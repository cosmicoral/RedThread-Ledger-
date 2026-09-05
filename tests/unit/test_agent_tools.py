from agent.sanitize import sanitize_search_query
from agent.tools import (
    EXCLUDED_SEARCH_SHEETS,
    SEARCH_TARGETS,
    get_transaction_evidence,
    search_external_sources,
    search_internal_master_data,
    validate_proposed_journal,
)
from runtime import process_all


def test_evidence_omits_account_identifiers() -> None:
    results = process_all()
    item = next(row for row in results if row.status.value == "needs_review")
    payload = get_transaction_evidence(item.transaction_id)
    assert "account_number" not in payload
    assert "bank_account" not in payload
    assert item.evidence.narrative == payload["narrative"]
    assert item.evidence.document_name == payload["document_name"]
    if item.evidence.account_number:
        assert item.evidence.account_number not in str(payload.values())


def test_internal_search_returns_sheet_references() -> None:
    process_all()
    payload = search_internal_master_data("Trentbeck Audit", "vendor")
    assert payload["candidates"]
    top = payload["candidates"][0]
    assert top["sheet"] == "Vendor Master List"
    assert "Vendor Master List" in top["source"]
    assert top["score"] > 0


def test_search_query_strips_accounts_and_full_narratives() -> None:
    narrative = (
        "BQVRFRPP, /FR6239723540911169279904595 CHARGE WAIVED, extra clause here"
    )
    cleaned = sanitize_search_query(
        "Pay 240-222731-030 IBAN LU355210240149813030 " + narrative,
        narrative=narrative,
    )
    assert "240-222731-030" not in cleaned
    assert "LU355210240149813030" not in cleaned
    assert narrative not in cleaned
    assert cleaned


def test_external_search_never_sends_account_or_full_narrative() -> None:
    narrative = "BQVRFRPP, /FR6239723540911169279904595 CHARGE WAIVED, extra clause here"
    seen: list[str] = []

    def search_fn(query: str) -> dict:
        seen.append(query)
        return {"results": [], "citations": []}

    payload = search_external_sources(
        "240-222731-030 IBAN LU355210240149813030 " + narrative,
        narrative=narrative,
        search_fn=search_fn,
    )
    assert payload.get("error") != "search_unavailable"
    if seen:
        assert all(narrative not in query for query in seen)
        assert all("240-222731-030" not in query for query in seen)
        assert all("LU355210240149813030" not in query for query in seen)
    reduced = search_external_sources(narrative, narrative=narrative, search_fn=search_fn)
    assert reduced.get("error") != "search_unavailable"
    assert narrative not in (reduced.get("query") or "")
    assert "240-222731-030" not in (reduced.get("query") or "")


def test_internal_search_skips_account_identifier_sheets() -> None:
    for targets in SEARCH_TARGETS.values():
        sheets = {sheet for sheet, _key, _field in targets}
        assert sheets.isdisjoint(EXCLUDED_SEARCH_SHEETS)


def test_journal_validation_checks_balance_and_accounts() -> None:
    process_all()
    ok = validate_proposed_journal(
        {
            "currency": "EUR",
            "classification": "Vendor",
            "lines": [
                {
                    "account": "20500.4",
                    "transaction_type": "Accounts Payable",
                    "debit": 10,
                    "credit": 0,
                },
                {
                    "account": "10000",
                    "transaction_type": "Cash - Disbursed - EUR",
                    "debit": 0,
                    "credit": 10,
                },
            ],
        }
    )
    assert ok["valid"] is True
    bad = validate_proposed_journal(
        {
            "currency": "EUR",
            "classification": "Not A Real Class",
            "lines": [
                {"account": "missing", "debit": 5, "credit": 0},
                {"account": "10000", "debit": 0, "credit": 4},
            ],
        }
    )
    assert bad["valid"] is False
    assert bad["checks"]["balanced"] is False
    assert bad["checks"]["accounts_exist"] is False
