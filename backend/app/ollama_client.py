from __future__ import annotations

import time
from typing import Any

import httpx

from .config import settings


async def list_ollama_models() -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(f"{settings.ollama_url}/api/tags")
            response.raise_for_status()
            payload = response.json()
            return [m.get("name", "") for m in payload.get("models", []) if m.get("name")]
    except Exception:
        return [settings.default_model, "mistral:7b"]


async def generate(
    model: str,
    prompt: str,
    system: str,
    temperature: float = 0.2,
) -> tuple[str, dict[str, Any]]:
    started = time.perf_counter()
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {
            "temperature": temperature,
            # Keep responses short enough for CPU-only environments.
            "num_predict": 96,
            "num_ctx": 2048,
        },
    }

    timeout = httpx.Timeout(connect=30.0, read=1800.0, write=60.0, pool=60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{settings.ollama_url}/api/generate", json=payload)
        response.raise_for_status()
        data = response.json()

    elapsed = max(time.perf_counter() - started, 1e-6)
    output = data.get("response", "")
    eval_count = int(data.get("eval_count", 0) or 0)
    tok_s = eval_count / elapsed if eval_count > 0 else 0.0

    meta = {
        "total_duration_ns": data.get("total_duration"),
        "eval_count": eval_count,
        "eval_duration_ns": data.get("eval_duration"),
        "tokens_per_second": round(tok_s, 2),
    }
    return output, meta
