from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

from .config import settings


@dataclass
class RetrievedChunk:
    chunk_id: int
    score: float


class RagIndex:
    def __init__(self) -> None:
        self.embedder = SentenceTransformer(settings.embed_model)
        self.dim = self.embedder.get_sentence_embedding_dimension()
        self.index = faiss.IndexFlatIP(self.dim)
        self.chunk_ids: list[int] = []
        self._load()

    def _meta_path(self) -> Path:
        return settings.faiss_index_path.with_suffix(".meta.pkl")

    def _load(self) -> None:
        if settings.faiss_index_path.exists():
            self.index = faiss.read_index(str(settings.faiss_index_path))
        if self._meta_path().exists():
            self.chunk_ids = pickle.loads(self._meta_path().read_bytes())

    def _save(self) -> None:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(settings.faiss_index_path))
        self._meta_path().write_bytes(pickle.dumps(self.chunk_ids))

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        vectors = self.embedder.encode(texts, normalize_embeddings=True)
        return np.array(vectors, dtype="float32")

    def rebuild(self, chunk_rows: list[dict[str, Any]]) -> None:
        self.index = faiss.IndexFlatIP(self.dim)
        self.chunk_ids = []
        if not chunk_rows:
            self._save()
            return
        texts = [r["text"] for r in chunk_rows]
        ids = [int(r["id"]) for r in chunk_rows]
        vectors = self.embed_texts(texts)
        self.index.add(vectors)
        self.chunk_ids = ids
        self._save()

    def add(self, chunk_ids: list[int], texts: list[str]) -> None:
        if not texts:
            return
        vectors = self.embed_texts(texts)
        self.index.add(vectors)
        self.chunk_ids.extend(chunk_ids)
        self._save()

    def search(self, query: str, top_k: int = 4) -> list[RetrievedChunk]:
        if self.index.ntotal == 0:
            return []
        q = self.embed_texts([query])
        scores, ids = self.index.search(q, top_k)
        results: list[RetrievedChunk] = []
        for score, idx in zip(scores[0], ids[0]):
            if idx == -1:
                continue
            if idx >= len(self.chunk_ids):
                continue
            results.append(RetrievedChunk(chunk_id=self.chunk_ids[idx], score=float(score)))
        return results


def parse_file_to_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    raise ValueError(f"Unsupported file type: {suffix}")


def chunk_text(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    if not text:
        return []

    chunks: list[dict[str, Any]] = []
    start = 0
    size = settings.chunk_size
    overlap = settings.chunk_overlap
    idx = 0

    while start < len(text):
        end = min(start + size, len(text))
        piece = text[start:end]
        chunks.append(
            {
                "chunk_index": idx,
                "text": piece,
                "start_offset": start,
                "end_offset": end,
            }
        )
        if end == len(text):
            break
        start = max(0, end - overlap)
        idx += 1

    return chunks
