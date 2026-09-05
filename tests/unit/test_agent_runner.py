from agent.client import FunctionCall, ModelTurn, SequenceModel
from agent.runner import run_agent_review
from agent.tools import escalate_to_human
from models import ReviewStatus
from runtime import get_transaction, process_all


def _needs_review_id() -> str:
    results = process_all()
    return next(item.transaction_id for item in results if item.status == ReviewStatus.NEEDS_REVIEW)


def _ready_id() -> str:
    results = process_all()
    return next(item.transaction_id for item in results if item.status == ReviewStatus.READY_TO_POST)


def test_escalate_to_human_is_unresolved() -> None:
    payload = escalate_to_human("contradictory names", "legal entity confirmation")
    assert payload["status"] == "needs_human_review"
    assert payload["escalated"] is True


def test_mocked_agent_suggests_without_changing_original(monkeypatch) -> None:
    transaction_id = _needs_review_id()
    original = get_transaction(transaction_id)
    assert original is not None
    snapshot = original.model_dump()
    monkeypatch.setattr("agent.runner.settings.agent_enabled", True)
    model = SequenceModel(
        [
            ModelTurn(
                function_calls=[
                    FunctionCall("get_transaction_evidence", {"transaction_id": transaction_id})
                ]
            ),
            ModelTurn(
                function_calls=[
                    FunctionCall(
                        "search_internal_master_data",
                        {"query": "Trentbeck", "entity_type": "vendor"},
                    )
                ]
            ),
            ModelTurn(
                function_calls=[
                    FunctionCall(
                        "search_external_sources",
                        {"entity_name": "Trentbeck Audit", "entity_type": "vendor"},
                    )
                ]
            ),
            ModelTurn(
                text=(
                    '{"status":"agent_suggested","summary":"Possible vendor match from master data.",'
                    '"proposed_fields":{"counterparty":"Trentbeck Audit - Lu","classification":"Vendor"},'
                    '"proposed_journal_lines":['
                    '{"account":"20500.4","transaction_type":"Accounts Payable","debit":10,"credit":0,"memo":"agent"},'
                    '{"account":"10000","transaction_type":"Cash - Disbursed - EUR","debit":0,"credit":10,"memo":"agent"}'
                    '],"confidence":0.64,"unresolved_questions":["Confirm the vendor legal name"],'
                    '"internal_evidence":[],"external_citations":[]}'
                )
            ),
        ]
    )
    review = run_agent_review(
        transaction_id,
        model=model,
        search_fn=lambda query: {
            "results": [{"text": "Audit firm"}],
            "citations": [{"title": "ignored", "uri": "https://not-grounded.example"}],
            "grounding_citations": [{"title": "Example", "uri": "https://example.com", "snippet": query}],
        },
    )
    assert review.status.value == "agent_suggested"
    assert review.status.value != "ready_to_post"
    assert review.human_approval_required is True
    assert review.deterministic_validation.valid is True
    assert [item.tool for item in review.tool_trace] == [
        "get_transaction_evidence",
        "search_internal_master_data",
        "search_external_sources",
    ]
    assert review.external_citations[0].uri == "https://example.com"
    assert get_transaction(transaction_id).model_dump() == snapshot
    assert original.status == ReviewStatus.NEEDS_REVIEW


def test_disabled_agent_falls_back_without_model(monkeypatch) -> None:
    transaction_id = _needs_review_id()
    monkeypatch.setattr("agent.runner.settings.agent_enabled", False)
    called = {"n": 0}

    class Boom:
        def generate(self, contents):
            called["n"] += 1
            raise AssertionError("Gemini must not be called when disabled")

    review = run_agent_review(transaction_id, model=Boom())
    assert review.fallback is True
    assert review.status.value == "needs_human_review"
    assert called["n"] == 0


def test_ready_to_post_is_not_agent_reviewed() -> None:
    review = run_agent_review(_ready_id())
    assert review.fallback is True
    assert "Needs-review" in review.summary


def test_model_ready_to_post_is_coerced(monkeypatch) -> None:
    transaction_id = _needs_review_id()
    monkeypatch.setattr("agent.runner.settings.agent_enabled", True)
    model = SequenceModel(
        [
            ModelTurn(
                text=(
                    '{"status":"ready_to_post","summary":"Should not post.",'
                    '"proposed_fields":{"classification":"Vendor"},'
                    '"proposed_journal_lines":['
                    '{"account":"20500.4","transaction_type":"Accounts Payable","debit":10,"credit":0,"memo":"x"},'
                    '{"account":"10000","transaction_type":"Cash - Disbursed - EUR","debit":0,"credit":10,"memo":"x"}'
                    '],"confidence":0.9}'
                )
            )
        ]
    )
    review = run_agent_review(transaction_id, model=model)
    assert review.status.value == "agent_suggested"
    assert review.status.value != "ready_to_post"
    assert review.human_approval_required is True
    assert get_transaction(transaction_id).status == ReviewStatus.NEEDS_REVIEW


def test_tool_rounds_are_capped_at_four(monkeypatch) -> None:
    transaction_id = _needs_review_id()
    monkeypatch.setattr("agent.runner.settings.agent_enabled", True)
    monkeypatch.setattr("agent.runner.settings.agent_max_tool_rounds", 4)
    turns = [
        ModelTurn(
            function_calls=[
                FunctionCall("get_transaction_evidence", {"transaction_id": transaction_id})
            ]
        )
        for _ in range(6)
    ]
    model = SequenceModel(turns)
    review = run_agent_review(transaction_id, model=model)
    assert model.calls == 4
    assert len(review.tool_trace) == 4
    assert review.status.value == "needs_human_review"
    assert review.status.value != "ready_to_post"


def test_model_authored_citation_urls_are_ignored(monkeypatch) -> None:
    transaction_id = _needs_review_id()
    monkeypatch.setattr("agent.runner.settings.agent_enabled", True)
    model = SequenceModel(
        [
            ModelTurn(
                text=(
                    '{"status":"needs_human_review","summary":"No grounded sources.",'
                    '"proposed_fields":{},"proposed_journal_lines":[],"confidence":0.1,'
                    '"external_citations":[{"title":"evil","uri":"https://evil.example","snippet":"no"}]}'
                )
            )
        ]
    )
    review = run_agent_review(transaction_id, model=model)
    assert review.external_citations == []
    assert review.status.value == "needs_human_review"
    assert review.human_approval_required is True


def test_gemini_error_falls_back(monkeypatch) -> None:
    transaction_id = _needs_review_id()
    monkeypatch.setattr("agent.runner.settings.agent_enabled", True)
    monkeypatch.setattr("agent.runner.settings.gemini_api_key", "test-key")

    class Broken:
        def generate(self, contents):
            raise RuntimeError("provider down")

    review = run_agent_review(transaction_id, model=Broken())
    assert review.fallback is True
    assert review.status.value == "needs_human_review"
    assert "Gemini unavailable" in review.fallback_reason
