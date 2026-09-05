from __future__ import annotations

import re

ACCOUNT_NUMBER = re.compile(
    r"(?i)\b(?:IBAN\b|[A-Z]{2}\d{2}[A-Z0-9]{10,30}|\d{2,4}[- ]\d{5,}(?:[- ]\d{2,})+|\d{6,})"
)
AMOUNT_TOKEN = re.compile(r"-?[\d]{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+\.\d{2}")


def looks_like_full_narrative(query: str) -> bool:
    text = (query or "").strip()
    return len(text) > 80 and text.count(",") >= 2


def sanitize_search_query(query: str, *, narrative: str | None = None) -> str:
    """Strip account identifiers and refuse complete transaction narratives."""
    text = " ".join((query or "").split())
    if not text:
        return ""
    if narrative and text == " ".join(narrative.split()):
        text = narrative.split(",")[0].strip()
    elif looks_like_full_narrative(text):
        text = text.split(",")[0].strip()
    text = ACCOUNT_NUMBER.sub(" ", text)
    text = AMOUNT_TOKEN.sub(" ", text)
    text = " ".join(text.split())
    if len(text) > 80:
        text = text[:80].rsplit(" ", 1)[0]
    return text
