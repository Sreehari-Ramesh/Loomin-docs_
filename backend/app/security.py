import re


PATTERNS = {
    "api_key": re.compile(r"\b(?:sk|pk|AKIA)[A-Za-z0-9_-]{8,}\b"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "long_id": re.compile(r"\b\d{10,}\b"),
}


MASK = "[REDACTED]"


def sanitize_text(text: str) -> str:
    sanitized = text
    for pattern in PATTERNS.values():
        sanitized = pattern.sub(MASK, sanitized)
    return sanitized
