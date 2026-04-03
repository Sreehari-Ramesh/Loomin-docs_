from __future__ import annotations

import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .collab import CollaborationHub
from .config import settings
from .db import (
    delete_chunks_for_file,
    delete_file,
    ensure_default_document,
    get_all_chunks,
    get_chunk,
    get_document,
    get_file,
    init_db,
    insert_chunk,
    insert_file,
    list_chat,
    list_document_versions,
    list_documents,
    list_files,
    save_chat,
    touch_document_content,
    upsert_document,
)
from .ollama_client import generate, list_ollama_models
from .rag import RagIndex, chunk_text, parse_file_to_text
from .schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
    DocumentOut,
    DocumentUpsert,
    ModelSelectionRequest,
    TransformRequest,
    TransformResponse,
)
from .security import sanitize_text

app = FastAPI(title=settings.app_name, version=settings.app_version)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL_PROFILES = {
    "llama3:8b": 8192,
    "mistral:7b": 8192,
    "qwen2.5:7b": 32768,
}

rag = RagIndex()
collab = CollaborationHub()
active_model = settings.default_model


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / 4))


def context_window_for(model_name: str) -> int:
    return MODEL_PROFILES.get(model_name, 8192)


@app.on_event("startup")
def startup() -> None:
    init_db()
    ensure_default_document()
    rag.rebuild(get_all_chunks())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/models")
async def models() -> dict[str, object]:
    names = await list_ollama_models()
    merged = sorted(set(names + list(MODEL_PROFILES.keys())))
    return {"active": active_model, "available": merged, "profiles": MODEL_PROFILES}


@app.post("/models/select")
def select_model(payload: ModelSelectionRequest) -> dict[str, str]:
    global active_model
    active_model = payload.model
    return {"active": active_model}


@app.get("/files")
def files() -> dict[str, object]:
    return {"items": list_files()}


@app.delete("/files/{file_id}")
def remove_file(file_id: int) -> dict[str, object]:
    f = get_file(file_id)
    if not f:
        raise HTTPException(status_code=404, detail="File not found")

    path = Path(f["path"])
    if path.exists():
        path.unlink(missing_ok=True)

    delete_chunks_for_file(file_id)
    delete_file(file_id)
    rag.rebuild(get_all_chunks())
    return {"ok": True}


@app.post("/files/upload")
async def upload(file: UploadFile = File(...)) -> dict[str, object]:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in {".pdf", ".md", ".txt"}:
        raise HTTPException(status_code=400, detail="Only .pdf/.md/.txt files are allowed")

    data = await file.read()
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    disk_path = settings.uploads_dir / safe_name
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    disk_path.write_bytes(data)

    file_id = insert_file(file.filename or safe_name, str(disk_path), file.content_type or "application/octet-stream")

    raw_text = parse_file_to_text(disk_path)
    chunks = chunk_text(raw_text)
    chunk_ids: list[int] = []
    chunk_texts: list[str] = []

    for item in chunks:
        chunk_id = insert_chunk(
            file_id=file_id,
            chunk_index=item["chunk_index"],
            text=item["text"],
            start_offset=item["start_offset"],
            end_offset=item["end_offset"],
        )
        chunk_ids.append(chunk_id)
        chunk_texts.append(item["text"])

    rag.add(chunk_ids, chunk_texts)
    return {"file_id": file_id, "chunks_indexed": len(chunk_ids)}


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    request_id = uuid.uuid4().hex
    selected_model = payload.model or active_model
    clean_message = sanitize_text(payload.message)
    safe_document = sanitize_text(payload.document_content or "")

    t0 = time.perf_counter()
    hits = rag.search(clean_message, top_k=payload.top_k)
    retrieval_ms = int((time.perf_counter() - t0) * 1000)

    citations: list[Citation] = []
    contexts: list[str] = []
    for h in hits:
        chunk = get_chunk(h.chunk_id)
        if not chunk:
            continue
        snippet = chunk["text"][:250].replace("\n", " ")
        citations.append(
            Citation(
                chunk_id=chunk["id"],
                file_id=chunk["file_id"],
                filename=chunk["filename"],
                snippet=snippet,
            )
        )
        contexts.append(f"[chunk:{chunk['id']} file:{chunk['filename']}]\n{chunk['text']}")

    context_blob = "\n\n".join(contexts)
    system_prompt = (
        "You are Loomin assistant. Use only provided context for factual claims. "
        "If unknown, say you do not find it in local files. Always cite chunk IDs."
    )
    user_prompt = (
        f"Question:\n{clean_message}\n\n"
        f"Active document excerpt:\n{safe_document[:2500] if safe_document else '[none]'}\n\n"
        f"Retrieved context:\n{context_blob if context_blob else '[none]'}\n\n"
        "Respond with concise answer and include chunk ids like [chunk:12]."
    )

    answer, gen_meta = await generate(model=selected_model, prompt=user_prompt, system=system_prompt)

    input_tokens = estimate_tokens(user_prompt + system_prompt)
    output_tokens = estimate_tokens(answer)
    document_tokens = estimate_tokens(safe_document)
    retrieved_tokens = estimate_tokens(context_blob)
    context_window = context_window_for(selected_model)
    combined_context = document_tokens + retrieved_tokens

    metadata = {
        "request_id": request_id,
        "model": selected_model,
        "retrieval_ms": retrieval_ms,
        "generation_tokens_per_sec": gen_meta["tokens_per_second"],
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "document_tokens": document_tokens,
        "retrieved_tokens": retrieved_tokens,
        "context_window": context_window,
        "context_used_pct": round((combined_context / context_window) * 100, 2),
    }

    save_chat(
        request_id=request_id,
        user_message=clean_message,
        assistant_message=answer,
        model=selected_model,
        metadata=metadata,
    )

    return ChatResponse(request_id=request_id, answer=answer, citations=citations, metadata=metadata)


@app.get("/chat/history")
def chat_history() -> dict[str, object]:
    return {"items": list_chat()}


@app.post("/editor/transform", response_model=TransformResponse)
async def transform(payload: TransformRequest) -> TransformResponse:
    request_id = uuid.uuid4().hex
    selected_model = payload.model or active_model

    instruction_map = {
        "summarize": "Summarize the text in fewer words while preserving meaning.",
        "improve": "Improve clarity, grammar, and flow without changing intent.",
        "rewrite": "Rewrite the text with a professional tone while preserving meaning.",
    }
    instruction = instruction_map[payload.operation]
    clean = sanitize_text(payload.selected_text)

    prompt = (
        f"Instruction: {instruction}\n\n"
        f"Text:\n{clean}\n\n"
        "Return only the transformed text."
    )

    answer, gen_meta = await generate(
        model=selected_model,
        prompt=prompt,
        system="You are an expert writing assistant.",
    )

    metadata = {
        "request_id": request_id,
        "model": selected_model,
        "retrieval_ms": 0,
        "generation_tokens_per_sec": gen_meta["tokens_per_second"],
        "input_tokens": estimate_tokens(prompt),
        "output_tokens": estimate_tokens(answer),
    }

    if payload.apply_to_document and payload.document_id:
        existing = get_document(payload.document_id)
        if existing:
            new_content = existing["content"].replace(payload.selected_text, answer, 1)
            touch_document_content(payload.document_id, new_content)

    return TransformResponse(request_id=request_id, transformed_text=answer, metadata=metadata)


@app.get("/documents")
def documents() -> dict[str, object]:
    return {"items": list_documents()}


@app.post("/documents", response_model=DocumentOut)
def create_or_update_document(payload: DocumentUpsert, doc_id: int | None = None) -> DocumentOut:
    row = upsert_document(doc_id=doc_id, title=payload.title, content=payload.content)
    return DocumentOut(**row)


@app.get("/documents/{doc_id}", response_model=DocumentOut)
def document(doc_id: int) -> DocumentOut:
    row = get_document(doc_id)
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentOut(**row)


@app.get("/documents/{doc_id}/versions")
def document_versions(doc_id: int) -> dict[str, object]:
    return {"items": list_document_versions(doc_id)}


@app.websocket("/ws/documents/{doc_id}")
async def doc_socket(websocket: WebSocket, doc_id: int, client_id: str = "anon") -> None:
    doc = get_document(doc_id)
    if not doc:
        await websocket.accept()
        await websocket.close(code=1008)
        return

    await collab.connect(doc_id, websocket, client_id)
    peers = await collab.room_size(doc_id)
    await websocket.send_json({"type": "init", "content": doc["content"], "peers": peers})
    await collab.broadcast(doc_id, {"type": "presence", "peers": peers})

    try:
        while True:
            payload = await websocket.receive_json()
            msg_type = payload.get("type")
            if msg_type == "sync":
                content = str(payload.get("content", ""))
                touch_document_content(doc_id, content)
                await collab.broadcast(
                    doc_id,
                    {
                        "type": "sync",
                        "content": content,
                        "source": client_id,
                    },
                    sender=websocket,
                )
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        peers = await collab.disconnect(doc_id, websocket)
        await collab.broadcast(doc_id, {"type": "presence", "peers": peers})
