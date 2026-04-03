from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    chunk_id: int
    file_id: int
    filename: str
    snippet: str


class ChatRequest(BaseModel):
    message: str
    model: str | None = None
    top_k: int = Field(default=4, ge=1, le=10)
    document_content: str = ""


class ChatResponse(BaseModel):
    request_id: str
    answer: str
    citations: list[Citation]
    metadata: dict[str, Any]


class TransformRequest(BaseModel):
    operation: Literal["summarize", "improve", "rewrite"]
    selected_text: str
    document_id: int | None = None
    apply_to_document: bool = False
    model: str | None = None


class TransformResponse(BaseModel):
    request_id: str
    transformed_text: str
    metadata: dict[str, Any]


class DocumentUpsert(BaseModel):
    title: str
    content: str


class DocumentOut(BaseModel):
    id: int
    title: str
    content: str
    updated_at: str


class ModelSelectionRequest(BaseModel):
    model: str
