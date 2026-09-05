from pathlib import Path

from agent.client import (
    FunctionCall,
    ModelTurn,
    SDK_CONTENT_KEY,
    SequenceModel,
    contents_for_sdk,
    snapshot_model_content,
)
from agent.runner import run_agent_review
from agent.sanitize import format_provider_error
from agent.schemas import FUNCTION_DECLARATIONS
from models import ReviewStatus
from runtime import get_transaction, process_all

ROOT = Path(__file__).resolve().parents[2]
ACCOUNT = "240-222731-030"
NARRATIVE = "BQVRFRPP, /FR6239723540911169279904595 CHARGE WAIVED, extra clause here"
FAKE_KEY = "AIzaSyDummyTestKeyValueXXXXX123456"


def _needs_review_id() -> str:
    results = process_all()
    return next(item.transaction_id for item in results if item.status == ReviewStatus.NEEDS_REVIEW)


def _object_nodes(node: object, path: str = "$"):
    if isinstance(node, dict):
        if str(node.get("type") or "").upper() == "OBJECT":
            yield path, node
        for key, value in node.items():
            yield from _object_nodes(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _object_nodes(value, f"{path}[{index}]")


def test_default_model_is_gemini_36() -> None:
    settings_text = (ROOT / "backend" / "settings.py").read_text()
    example = (ROOT / ".env.example").read_text()
    requirements = (ROOT / "backend" / "requirements.txt").read_text()
    assert 'gemini_model: str = "gemini-3.6-flash"' in settings_text
    assert "GEMINI_MODEL=gemini-3.6-flash" in example
    assert "gemini-2.5-flash" not in settings_text
    assert "gemini-2.5-flash" not in example
    assert "google-genai==2.22.0" in requirements
    assert "google-genai==1.52.0" not in requirements


def test_function_schemas_have_explicit_object_properties() -> None:
    proposal = None
    for declaration in FUNCTION_DECLARATIONS:
        for path, node in _object_nodes(declaration["parameters"], declaration["name"]):
            assert node.get("properties"), f"{path} is an OBJECT without properties"
            assert isinstance(node["properties"], dict) and node["properties"]
        if declaration["name"] == "validate_proposed_journal":
            proposal = declaration["parameters"]["properties"]["proposal"]
    assert proposal is not None
    assert set(proposal["properties"]) == {"currency", "classification", "lines"}
    line = proposal["properties"]["lines"]["items"]
    assert set(line["properties"]) >= {
        "account",
        "transaction_type",
        "debit",
        "credit",
        "memo",
    }


def test_thought_signatures_and_call_ids_survive_multiple_tool_rounds(monkeypatch) -> None:
    transaction_id = _needs_review_id()
    snapshot = get_transaction(transaction_id).model_dump()
    monkeypatch.setattr("agent.runner.settings.agent_enabled", True)
    first_content = {
        "role": "model",
        "parts": [
            {
                "thought_signature": "sig-round-1",
                "function_call": {
                    "name": "get_transaction_evidence",
                    "args": {"transaction_id": transaction_id},
                    "id": "call-ev-1",
                },
            }
        ],
    }
    second_content = {
        "role": "model",
        "parts": [
            {
                "thought_signature": "sig-round-2",
                "function_call": {
                    "name": "search_internal_master_data",
                    "args": {"query": "Trentbeck", "entity_type": "vendor"},
                    "id": "call-search-2",
                },
            }
        ],
    }
    model = SequenceModel(
        [
            ModelTurn(
                function_calls=[
                    FunctionCall(
                        "get_transaction_evidence",
                        {"transaction_id": transaction_id},
                        id="call-ev-1",
                        thought_signature="sig-round-1",
                    )
                ],
                model_content=first_content,
            ),
            ModelTurn(
                function_calls=[
                    FunctionCall(
                        "search_internal_master_data",
                        {"query": "Trentbeck", "entity_type": "vendor"},
                        id="call-search-2",
                        thought_signature="sig-round-2",
                    )
                ],
                model_content=second_content,
            ),
            ModelTurn(
                text=(
                    '{"status":"needs_human_review","summary":"Need a person.",'
                    '"proposed_fields":{},"proposed_journal_lines":[],"confidence":0.2}'
                )
            ),
        ]
    )
    review = run_agent_review(transaction_id, model=model)
    assert model.calls == 3
    second_request = model.received[1]
    assert first_content in second_request
    first_response = next(
        part["function_response"]
        for message in second_request
        for part in message.get("parts", [])
        if "function_response" in part
    )
    assert first_response["id"] == "call-ev-1"
    third_request = model.received[2]
    signatures = [
        part.get("thought_signature")
        for message in third_request
        for part in message.get("parts", [])
        if part.get("thought_signature")
    ]
    call_ids = [
        (part.get("function_call") or part.get("function_response") or {}).get("id")
        for message in third_request
        for part in message.get("parts", [])
        if "function_call" in part or "function_response" in part
    ]
    assert signatures == ["sig-round-1", "sig-round-2"]
    assert "call-ev-1" in call_ids
    assert "call-search-2" in call_ids
    assert review.human_approval_required is True
    assert review.status.value != "ready_to_post"
    assert get_transaction(transaction_id).model_dump() == snapshot


def test_contents_for_sdk_preserves_signatures_ids_and_exact_content() -> None:
    from google.genai import types

    original = types.Content(
        role="model",
        parts=[
            types.Part(
                thought_signature=b"keep-exact",
                function_call=types.FunctionCall(
                    name="get_transaction_evidence",
                    args={"transaction_id": "t1"},
                    id="call-exact",
                ),
            )
        ],
    )
    history = [
        {"role": "user", "parts": [{"text": "investigate"}]},
        {
            "role": "model",
            "parts": [
                {
                    "thought_signature": b"sig-bytes",
                    "function_call": {
                        "name": "get_transaction_evidence",
                        "args": {"transaction_id": "t1"},
                        "id": "call-1",
                    },
                }
            ],
        },
        {
            "role": "user",
            "parts": [
                {
                    "function_response": {
                        "name": "get_transaction_evidence",
                        "response": {"ok": True},
                        "id": "call-1",
                    }
                }
            ],
        },
        {
            "role": "model",
            "parts": [{"function_call": {"name": "ignored", "args": {}, "id": "no"}}],
            SDK_CONTENT_KEY: original,
        },
    ]
    converted = contents_for_sdk(history)
    model_part = converted[1].parts[0]
    assert model_part.thought_signature == b"sig-bytes"
    assert model_part.function_call.id == "call-1"
    assert model_part.function_call.name == "get_transaction_evidence"
    assert converted[2].parts[0].function_response.id == "call-1"
    assert converted[3] is original
    snap = snapshot_model_content(original)
    assert snap[SDK_CONTENT_KEY] is original
    assert snap["parts"][0]["function_call"]["id"] == "call-exact"


def test_provider_error_logs_status_without_secrets(monkeypatch, caplog) -> None:
    transaction_id = _needs_review_id()
    snapshot = get_transaction(transaction_id).model_dump()
    monkeypatch.setattr("agent.runner.settings.agent_enabled", True)
    monkeypatch.setattr("agent.runner.settings.gemini_api_key", "test-key")

    class ClientError(Exception):
        def __init__(self) -> None:
            self.code = 400
            self.status = "INVALID_ARGUMENT"
            self.message = (
                f"Invalid function schema. key={FAKE_KEY} account={ACCOUNT} "
                f"narrative={NARRATIVE}"
            )
            super().__init__(self.message)

    class Broken:
        def generate(self, contents):
            raise ClientError()

    caplog.set_level("WARNING", logger="redthread.agent")
    review = run_agent_review(transaction_id, model=Broken())
    assert review.fallback is True
    assert review.status.value == "needs_human_review"
    assert review.human_approval_required is True
    assert "status=400" in review.fallback_reason
    assert "code=INVALID_ARGUMENT" in review.fallback_reason
    assert FAKE_KEY not in review.fallback_reason
    assert ACCOUNT not in review.fallback_reason
    assert NARRATIVE not in review.fallback_reason
    assert FAKE_KEY not in caplog.text
    assert ACCOUNT not in caplog.text
    assert NARRATIVE not in caplog.text
    assert "status=400" in caplog.text
    assert "INVALID_ARGUMENT" in caplog.text
    assert get_transaction(transaction_id).model_dump() == snapshot


def test_format_provider_error_redacts_request_contents() -> None:
    class ClientError(Exception):
        code = 400
        status = "INVALID_ARGUMENT"
        message = f"GEMINI_API_KEY={FAKE_KEY} {ACCOUNT} {NARRATIVE}"

    log_line, ui_reason = format_provider_error(ClientError())
    assert "status=400" in ui_reason
    assert "code=INVALID_ARGUMENT" in ui_reason
    assert FAKE_KEY not in log_line
    assert ACCOUNT not in log_line
    assert NARRATIVE not in log_line
    assert FAKE_KEY not in ui_reason
    assert ACCOUNT not in ui_reason
    assert NARRATIVE not in ui_reason
