from agent.sanitize import build_external_search_query, sanitize_search_query
from agent.tools import (
    EXCLUDED_SEARCH_SHEETS,
    SEARCH_TARGETS,
    dispatch_tool,
    get_transaction_evidence,
    search_external_sources,
    search_internal_master_data,
    validate_proposed_journal,
)
from runtime import process_all

ACCOUNT = "240-222731-030"
IBAN = "LU355210240149813030"
NARRATIVE = "BQVRFRPP, /FR6239723540911169279904595 CHARGE WAIVED, extra clause here"


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
    cleaned = sanitize_search_query("Pay " + ACCOUNT + " IBAN " + IBAN + " " + NARRATIVE)
    assert ACCOUNT not in cleaned
    assert IBAN not in cleaned
    assert NARRATIVE not in cleaned


def test_server_builds_structured_external_query() -> None:
    seen: list[str] = []

    def search_fn(query: str) -> dict:
        seen.append(query)
        return {
            "results": [{"text": "ok"}],
            "grounding_citations": [
                {"title": "Example", "uri": "https://example.com", "snippet": "ignore"}
            ],
        }

    payload = search_external_sources(
        entity_name="Trentbeck Audit",
        entity_type="vendor",
        jurisdiction="Luxembourg",
        search_fn=search_fn,
    )
    assert seen == ["Trentbeck Audit vendor Luxembourg"]
    assert payload["citations"] == [
        {"title": "Example", "uri": "https://example.com", "snippet": ""}
    ]
    assert "query" not in payload
    assert "Trentbeck" not in payload["query_log"] or "*" in payload["query_log"]


def test_external_search_rejects_account_narrative_and_freeform_query() -> None:
    seen: list[str] = []

    def search_fn(query: str) -> dict:
        seen.append(query)
        return {"grounding_citations": [{"title": "x", "uri": "https://example.com"}]}

    rejected = [
        search_external_sources(entity_name=ACCOUNT, entity_type="vendor", search_fn=search_fn),
        search_external_sources(entity_name=NARRATIVE, entity_type="vendor", search_fn=search_fn),
        search_external_sources(entity_name="Fee -10,000,000.00", entity_type="vendor", search_fn=search_fn),
        search_external_sources(entity_name="Payment 31 Mar 2026", entity_type="vendor", search_fn=search_fn),
        dispatch_tool(
            "search_external_sources",
            {"query": ACCOUNT + " " + NARRATIVE, "entity_type": "vendor"},
            search_fn=search_fn,
        ),
        dispatch_tool(
            "search_external_sources",
            {"entity_name": "Trentbeck", "entity_type": "vendor", "narrative": NARRATIVE},
            search_fn=search_fn,
        ),
    ]
    assert seen == []
    for payload in rejected:
        assert payload.get("escalated") is True
        assert payload.get("error") == "query_rejected"
        assert payload.get("status") == "needs_human_review"
        assert ACCOUNT not in str(payload)
        assert NARRATIVE not in str(payload)


def test_model_cannot_transmit_account_or_narrative_through_any_tool() -> None:
    seen: list[str] = []

    def search_fn(query: str) -> dict:
        seen.append(query)
        return {"grounding_citations": [{"title": "x", "uri": "https://example.com"}]}

    attempts = [
        ("search_external_sources", {"query": f"{ACCOUNT} {NARRATIVE}"}),
        ("search_external_sources", {"entity_name": ACCOUNT, "entity_type": "vendor"}),
        ("search_external_sources", {"entity_name": NARRATIVE, "entity_type": "vendor"}),
        ("search_external_sources", {"entity_name": "NI ABF", "entity_type": "vendor", "iban": IBAN}),
        ("search_internal_master_data", {"query": ACCOUNT, "entity_type": "vendor"}),
        ("search_internal_master_data", {"query": NARRATIVE, "entity_type": "vendor"}),
        ("escalate_to_human", {"reason": NARRATIVE, "missing_information": ACCOUNT}),
        (
            "validate_proposed_journal",
            {
                "proposal": {
                    "classification": "Vendor",
                    "lines": [
                        {"account": "20500.4", "debit": 10, "credit": 0, "memo": ACCOUNT},
                        {"account": "10000", "debit": 0, "credit": 10, "memo": NARRATIVE},
                    ],
                }
            },
        ),
    ]
    for name, arguments in attempts:
        payload = dispatch_tool(name, arguments, search_fn=search_fn)
        assert ACCOUNT not in str(payload.get("query") or "")
        assert NARRATIVE not in str(payload.get("query") or "")
        if name == "search_external_sources":
            assert payload.get("error") == "query_rejected"
            assert ACCOUNT not in str(payload)
            assert NARRATIVE not in str(payload)
    assert seen == []


def test_internal_search_rejects_account_like_queries() -> None:
    process_all()
    payload = search_internal_master_data(ACCOUNT, "vendor")
    assert payload["candidates"] == []
    assert payload.get("error") == "query_rejected"


def test_internal_search_skips_account_identifier_sheets() -> None:
    for targets in SEARCH_TARGETS.values():
        sheets = {sheet for sheet, _key, _field in targets}
        assert sheets.isdisjoint(EXCLUDED_SEARCH_SHEETS)


def test_build_query_requires_meaningful_entity_name() -> None:
    built = build_external_search_query(entity_name="240-222731-030", entity_type="vendor")
    assert built.rejected is True
    assert built.query == ""
    ok = build_external_search_query(entity_name="Trentbeck Audit", entity_type="vendor")
    assert ok.rejected is False
    assert ok.query == "Trentbeck Audit vendor"


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
