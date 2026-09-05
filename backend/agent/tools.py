from __future__ import annotations

import json
from typing import Any, Callable

from agent.models import ProposedJournalLine, ValidationResult
from agent.sanitize import sanitize_search_query
from journal import COUNTERPARTY_LEGS
from matching.text import rank_matches
from models import ReviewStatus, TransactionResult
from reference.loader import load_reference_data
from runtime import get_transaction
from settings import settings

TOOL_STEP = {
    "get_transaction_evidence": "evidence",
    "search_internal_master_data": "internal_lookup",
    "search_external_sources": "external_research",
    "validate_proposed_journal": "validation",
    "escalate_to_human": "recommendation",
}

SEARCH_TARGETS: dict[str, list[tuple[str, str, str]]] = {
    "legal_entity": [("Legal Entity Master List", "Legal Entity", "legal_entity")],
    "vendor": [("Vendor Master List", "Vendor", "vendor")],
    "investor": [("Investor Master List", "Investor", "investor")],
    "related_party": [("Related Party Master", "Related Party", "related_party")],
    "project": [("Project Code Report", "Project Code", "project_code")],
    "deal": [("Deal & Position Master List", "Deal Name", "deal")],
    "position": [("Deal & Position Master List", "Position", "position")],
    "account": [("CoA", "Trans Type", "account")],
    "counterparty": [
        ("Vendor Master List", "Vendor", "vendor"),
        ("Investor Master List", "Investor", "investor"),
        ("Related Party Master", "Related Party", "related_party"),
        ("Legal Entity Master List", "Legal Entity", "legal_entity"),
    ],
}

ALLOWED_CLASSIFICATIONS = {
    "Other",
    "Internal",
    "Investment",
    "Investment Transfer",
    "Related Party",
    "Vendor",
    "Investor",
    "Review",
}

ALLOWED_TRANSACTION_TYPES = {leg[0] for leg in COUNTERPARTY_LEGS.values()} | {
    "Cash - Disbursed",
    "Cash - Received",
    "Suspense (debit)",
}


# Never search sheets that carry bank-account identifiers.
EXCLUDED_SEARCH_SHEETS = frozenset({"Account Map", "Bank Account Report"})


def _refs() -> dict[str, list[dict[str, str]]]:
    return load_reference_data(settings.hackathon_reference_dir)


def get_transaction_evidence(transaction_id: str) -> dict[str, Any]:
    """Return narrative, document/page and extracted fields. Omits account identifiers."""
    item = get_transaction(transaction_id)
    if item is None:
        return {"error": "transaction_not_found"}
    return {
        "transaction_id": item.transaction_id,
        "date": item.date,
        "currency": item.currency,
        "amount": item.amount,
        "legal_entity": item.legal_entity,
        "narrative": item.evidence.narrative,
        "document_name": item.evidence.document_name,
        "page": item.evidence.page,
        "bank_reference": item.evidence.bank_reference,
        "customer_reference": item.evidence.customer_reference,
        "trn_type": item.evidence.trn_type,
        "pulled_counterparty": item.pulled_counterparty,
        "counterparty": item.counterparty,
        "related_party": item.related_party,
        "pulled_project": item.pulled_project,
        "project_code": item.project_code,
        "deal": item.deal,
        "position": item.position,
        "classification": item.classification,
        "status": item.status.value,
        "exception_reasons": [reason.value for reason in item.exception_reasons],
        "notes": item.notes,
        "deterministic_journal": [
            {
                "account": line.account,
                "transaction_type": line.transaction_type,
                "debit": line.debit,
                "credit": line.credit,
            }
            for line in item.journal_lines
        ],
    }


def search_internal_master_data(query: str, entity_type: str) -> dict[str, Any]:
    """Search allowlisted master CSVs and return ranked candidates with sheet names."""
    kind = (entity_type or "counterparty").strip().lower()
    targets = SEARCH_TARGETS.get(kind)
    if targets is None:
        targets = SEARCH_TARGETS["counterparty"]
    refs = _refs()
    ranked: list[dict[str, Any]] = []
    for sheet, key_field, field in targets:
        if sheet in EXCLUDED_SEARCH_SHEETS:
            continue
        matches = rank_matches(
            query,
            refs.get(sheet, []),
            sheet=sheet,
            key_field=key_field,
            field=field,
            limit=5,
        )
        for item in matches:
            ranked.append(
                {
                    "sheet": item.sheet,
                    "field": item.field,
                    "key": item.key,
                    "label": item.label,
                    "score": item.score,
                    "source": f"{item.sheet}:{key_field}",
                }
            )
    ranked.sort(key=lambda row: (-float(row["score"]), len(str(row["label"]))))
    return {"query": query, "entity_type": kind, "candidates": ranked[:8]}


def _parse_proposal(proposal: Any) -> dict[str, Any]:
    if isinstance(proposal, str):
        return json.loads(proposal)
    if isinstance(proposal, dict):
        return proposal
    raise ValueError("proposal must be an object or JSON string")


def validate_proposed_journal(proposal: Any, transaction: TransactionResult | None = None) -> dict[str, Any]:
    """Deterministically validate debit/credit, accounts, currency, fields and mappings."""
    result = ValidationResult()
    try:
        payload = _parse_proposal(proposal)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        result.errors.append(f"proposal_unreadable: {exc}")
        return result.model_dump()

    raw_lines = payload.get("lines") or payload.get("journal_lines") or []
    lines: list[ProposedJournalLine] = []
    for row in raw_lines:
        if not isinstance(row, dict):
            result.errors.append("each journal line must be an object")
            continue
        lines.append(ProposedJournalLine.model_validate(row))

    result.checks["two_lines"] = len(lines) == 2
    if not result.checks["two_lines"]:
        result.errors.append("exactly two journal lines are required")

    debit = round(sum(line.debit for line in lines), 2)
    credit = round(sum(line.credit for line in lines), 2)
    result.checks["balanced"] = debit == credit and debit > 0
    if not result.checks["balanced"]:
        result.errors.append("debit and credit must balance and be non-zero")

    refs = _refs()
    accounts = {
        row.get("Account") or row.get("GL Account Code")
        for row in refs.get("CoA", [])
        if row.get("Account") or row.get("GL Account Code")
    }
    trans_types = {row.get("Trans Type") for row in refs.get("CoA", []) if row.get("Trans Type")}
    missing_accounts: list[str] = []
    missing_fields = False
    mapping_ok = True
    for line in lines:
        if not line.account or (line.debit <= 0 and line.credit <= 0):
            missing_fields = True
        if line.account and line.account not in accounts:
            missing_accounts.append(line.account)
        if line.transaction_type and line.transaction_type not in trans_types:
            if line.transaction_type not in ALLOWED_TRANSACTION_TYPES and not any(
                line.transaction_type.startswith(prefix) for prefix in ("Cash - Disbursed", "Cash - Received")
            ):
                mapping_ok = False
    result.checks["required_fields"] = not missing_fields
    result.checks["accounts_exist"] = not missing_accounts
    if missing_fields:
        result.errors.append("each line needs an account and a debit or credit")
    if missing_accounts:
        result.errors.append(f"unknown accounts: {', '.join(missing_accounts)}")

    classification = str(payload.get("classification") or "")
    result.checks["allowed_classification"] = (not classification) or classification in ALLOWED_CLASSIFICATIONS
    if classification and classification not in ALLOWED_CLASSIFICATIONS:
        result.errors.append(f"classification {classification!r} is not an allowed mapping")
        mapping_ok = False
    result.checks["allowed_mappings"] = mapping_ok
    if not mapping_ok and "unknown accounts" not in " ".join(result.errors):
        if not any("allowed mapping" in error or "classification" in error for error in result.errors):
            result.errors.append("transaction type is not in the allowed mapping or CoA")

    currency = str(payload.get("currency") or "")
    currency_ok = True
    if transaction and currency and transaction.currency and currency != transaction.currency:
        currency_ok = False
        result.errors.append("currency does not match the source transaction")
    result.checks["currency"] = currency_ok

    result.valid = not result.errors
    return result.model_dump()


def search_external_sources(
    query: str,
    *,
    narrative: str | None = None,
    search_fn: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Grounded web corroboration. Query is sanitized before any external call."""
    cleaned = sanitize_search_query(query, narrative=narrative)
    full_narrative = " ".join((narrative or "").split())
    if not cleaned or (full_narrative and cleaned == full_narrative):
        return {
            "error": "query_rejected",
            "query": "",
            "results": [],
            "citations": [],
        }
    if search_fn is None:
        return {
            "error": "search_unavailable",
            "query": cleaned,
            "results": [],
            "citations": [],
        }
    payload = search_fn(cleaned)
    payload["query"] = cleaned
    return payload


def escalate_to_human(reason: str, missing_information: str) -> dict[str, Any]:
    """Return a clear unresolved result when evidence is insufficient or contradictory."""
    return {
        "escalated": True,
        "reason": reason,
        "missing_information": missing_information,
        "status": "needs_human_review",
    }


def dispatch_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    transaction: TransactionResult | None = None,
    search_fn: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if name == "get_transaction_evidence":
        return get_transaction_evidence(str(arguments.get("transaction_id") or ""))
    if name == "search_internal_master_data":
        return search_internal_master_data(
            str(arguments.get("query") or ""),
            str(arguments.get("entity_type") or "counterparty"),
        )
    if name == "validate_proposed_journal":
        return validate_proposed_journal(arguments.get("proposal") or arguments, transaction)
    if name == "search_external_sources":
        return search_external_sources(
            str(arguments.get("query") or ""),
            narrative=transaction.evidence.narrative if transaction else None,
            search_fn=search_fn,
        )
    if name == "escalate_to_human":
        return escalate_to_human(
            str(arguments.get("reason") or ""),
            str(arguments.get("missing_information") or ""),
        )
    return {"error": f"unknown_tool:{name}"}


def require_needs_review(item: TransactionResult) -> str | None:
    if item.status != ReviewStatus.NEEDS_REVIEW:
        return "Agent review is only available for Needs-review transactions"
    return None
