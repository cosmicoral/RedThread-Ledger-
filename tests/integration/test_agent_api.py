from fastapi.testclient import TestClient

from agent.client import FunctionCall, ModelTurn, SequenceModel
from api.main import app
from models import ReviewStatus
from runtime import current_results, process_all

client = TestClient(app)


def _needs_review_id() -> str:
    process_all()
    return next(
        item.transaction_id
        for item in current_results()
        if item.status == ReviewStatus.NEEDS_REVIEW
    )


def test_agent_review_endpoint_uses_mocked_gemini(monkeypatch) -> None:
    transaction_id = _needs_review_id()
    monkeypatch.setattr("agent.runner.settings.agent_enabled", True)
    monkeypatch.setattr("agent.runner.settings.gemini_api_key", "test-not-a-real-key")
    model = SequenceModel(
        [
            ModelTurn(
                function_calls=[
                    FunctionCall("escalate_to_human", {
                        "reason": "Ambiguous counterparty",
                        "missing_information": "Unique vendor legal name",
                    })
                ]
            )
        ]
    )
    monkeypatch.setattr("agent.runner.GeminiModel", lambda: model)
    before = client.get(f"/api/transactions/{transaction_id}").json()
    response = client.post(f"/api/transactions/{transaction_id}/agent-review")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_human_review"
    assert body["status"] != "ready_to_post"
    assert body["human_approval_required"] is True
    assert body["tool_trace"][0]["tool"] == "escalate_to_human"
    after = client.get(f"/api/transactions/{transaction_id}").json()
    assert after == before
    stored = client.get(f"/api/transactions/{transaction_id}/agent-review")
    assert stored.status_code == 200
    assert stored.json()["summary"]


def test_queue_and_health_do_not_require_gemini() -> None:
    health = client.get("/api/health").json()
    queue = client.get("/api/queue").json()
    assert health["agent_enabled"] is False
    assert queue["agent_enabled"] is False
    assert queue["total"] == 100
