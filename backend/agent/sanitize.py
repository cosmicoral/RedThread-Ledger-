from __future__ import annotations

import re
from dataclasses import dataclass

ALLOWED_ENTITY_TYPES = frozenset(
    {
        "vendor",
        "legal_entity",
        "investor",
        "related_party",
        "project",
        "counterparty",
        "fund",
        "advisor",
        "administrator",
    }
)
ALLOWED_SEARCH_FIELDS = frozenset(
    {"entity_name", "entity_type", "jurisdiction", "project_name"}
)

MAX_ENTITY_NAME = 48
MAX_JURISDICTION = 32
MAX_PROJECT_NAME = 40

ACCOUNT_NUMBER = re.compile(
    r"(?i)\b(?:IBAN\b|[A-Z]{2}\d{2}[A-Z0-9]{10,30}|\d{2,4}[- ]\d{5,}(?:[- ]\d{2,})+|\d{6,})"
)
DIGIT_RUN = re.compile(r"\d{4,}")
AMOUNT_TOKEN = re.compile(r"-?[\d]{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+\.\d{2}")
DATE_TOKEN = re.compile(
    r"(?i)\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b"
    r"|\b\d{4}-\d{2}-\d{2}\b"
    r"|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"
)
TX_REF = re.compile(
    r"(?i)\b(?:NONREF|CHARGE WAIVED|CHARGES FOR|TFR[+-]?|S\+P[-+]|SCT|CHG)\b|/\w{8,}"
)
ALLOWED_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9 .,&'/-]*$")
ALLOWED_JURISDICTION = re.compile(r"^[A-Za-z][A-Za-z .'-]*$")


def looks_like_full_narrative(query: str) -> bool:
    text = (query or "").strip()
    return len(text) > 60 and text.count(",") >= 2


def looks_like_account_or_narrative(value: str) -> bool:
    text = " ".join((value or "").split())
    if not text:
        return False
    return bool(
        looks_like_full_narrative(text)
        or ACCOUNT_NUMBER.search(text)
        or DIGIT_RUN.search(text)
        or AMOUNT_TOKEN.search(text)
        or DATE_TOKEN.search(text)
        or TX_REF.search(text)
    )


def redact_for_log(value: str) -> str:
    """Safe log fragment: no digit runs and no long narrative."""
    text = " ".join((value or "").split())
    text = ACCOUNT_NUMBER.sub("#", text)
    text = DIGIT_RUN.sub("#", text)
    text = AMOUNT_TOKEN.sub("#", text)
    if len(text) <= 4:
        return (text[:1] + "***") if text else "-"
    return text[:3] + "*" * min(8, max(0, len(text) - 3))


@dataclass(frozen=True)
class BuiltSearchQuery:
    query: str
    query_log: str
    rejected: bool
    reason: str = ""


def _clean_name(value: str, *, max_len: int) -> str:
    text = " ".join((value or "").split())
    if not text or len(text) > max_len:
        return ""
    if looks_like_account_or_narrative(text):
        return ""
    if not ALLOWED_NAME.fullmatch(text):
        return ""
    letters = re.sub(r"[^A-Za-z]", "", text)
    if len(letters) < 4:
        return ""
    return text


def _clean_jurisdiction(value: str) -> str:
    text = " ".join((value or "").split())
    if not text or len(text) > MAX_JURISDICTION:
        return ""
    if looks_like_account_or_narrative(text) or not ALLOWED_JURISDICTION.fullmatch(text):
        return ""
    return text


def build_external_search_query(
    *,
    entity_name: str,
    entity_type: str,
    jurisdiction: str = "",
    project_name: str = "",
    extra_fields: frozenset[str] | set[str] | None = None,
) -> BuiltSearchQuery:
    """Build the Google Search string on the server. Reject unsafe fields."""
    extras = {str(item) for item in (extra_fields or set()) if item}
    if extras:
        return BuiltSearchQuery(
            query="",
            query_log="rejected:unsupported_fields",
            rejected=True,
            reason="unsupported_fields",
        )
    kind = (entity_type or "").strip().lower()
    if kind not in ALLOWED_ENTITY_TYPES:
        return BuiltSearchQuery(
            query="",
            query_log="rejected:entity_type",
            rejected=True,
            reason="unsupported_entity_type",
        )
    name = _clean_name(entity_name, max_len=MAX_ENTITY_NAME)
    if not name:
        return BuiltSearchQuery(
            query="",
            query_log="rejected:entity_name",
            rejected=True,
            reason="entity_name_removed",
        )
    place = _clean_jurisdiction(jurisdiction) if jurisdiction else ""
    if jurisdiction and not place:
        return BuiltSearchQuery(
            query="",
            query_log="rejected:jurisdiction",
            rejected=True,
            reason="jurisdiction_removed",
        )
    project = _clean_name(project_name, max_len=MAX_PROJECT_NAME) if project_name else ""
    if project_name and not project:
        return BuiltSearchQuery(
            query="",
            query_log="rejected:project_name",
            rejected=True,
            reason="project_name_removed",
        )
    parts = [name, kind.replace("_", " ")]
    if place:
        parts.append(place)
    if project:
        parts.append(project)
    query = " ".join(parts)
    return BuiltSearchQuery(
        query=query,
        query_log=f"type={kind} name={redact_for_log(name)}",
        rejected=False,
    )


def sanitize_search_query(query: str, *, narrative: str | None = None) -> str:
    """Legacy helper used by tests for raw-string rejection behaviour."""
    del narrative
    if looks_like_account_or_narrative(query):
        return ""
    return _clean_name(query, max_len=MAX_ENTITY_NAME)
