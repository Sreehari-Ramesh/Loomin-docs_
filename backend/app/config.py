import os
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "Loomin Docs API"
    app_version: str = "0.1.0"
    data_dir: Path = Path(os.getenv("DATA_DIR", "data"))
    uploads_dir: Path = Path(os.getenv("UPLOADS_DIR", "data/uploads"))
    db_path: Path = Path(os.getenv("DB_PATH", "data/loomin.db"))
    faiss_index_path: Path = Path(os.getenv("FAISS_INDEX_PATH", "data/faiss.index"))
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    default_model: str = os.getenv("DEFAULT_MODEL", "llama3:8b")
    embed_model: str = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "800"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "120"))


settings = Settings()
