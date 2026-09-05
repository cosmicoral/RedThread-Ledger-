from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Protocol

from settings import settings

SDK_CONTENT_KEY = "_sdk_content"


@dataclass
class FunctionCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    id: str = ""
    thought_signature: Any = None


@dataclass
class ModelTurn:
    function_calls: list[FunctionCall] = field(default_factory=list)
    text: str = ""
    citations: list[dict[str, str]] = field(default_factory=list)
    model_content: dict[str, Any] | None = None


class AgentModel(Protocol):
    def generate(self, contents: list[Any]) -> ModelTurn:
        ...


def default_model_content(turn: ModelTurn) -> dict[str, Any]:
    """Build a complete model-content snapshot from an already-populated turn."""
    parts: list[dict[str, Any]] = []
    for call in turn.function_calls:
        part: dict[str, Any] = {
            "function_call": {
                "name": call.name,
                "args": dict(call.args),
                "id": call.id,
            }
        }
        if call.thought_signature is not None:
            part["thought_signature"] = call.thought_signature
        parts.append(part)
    if turn.text:
        parts.append({"text": turn.text})
    return {"role": "model", "parts": parts or [{"text": ""}]}


def snapshot_model_content(content: Any) -> dict[str, Any]:
    """Preserve every part, thought signature, order and function-call ID."""
    if isinstance(content, dict):
        snapshot = deepcopy({key: value for key, value in content.items() if key != SDK_CONTENT_KEY})
        if content.get(SDK_CONTENT_KEY) is not None:
            snapshot[SDK_CONTENT_KEY] = content[SDK_CONTENT_KEY]
        return snapshot
    parts: list[dict[str, Any]] = []
    for part in getattr(content, "parts", None) or []:
        if hasattr(part, "model_dump"):
            dumped = part.model_dump(exclude_none=True)
            if isinstance(dumped, dict):
                parts.append(dumped)
                continue
        item: dict[str, Any] = {}
        signature = getattr(part, "thought_signature", None)
        if signature is not None:
            item["thought_signature"] = signature
        thought = getattr(part, "thought", None)
        if thought:
            item["thought"] = thought
        function_call = getattr(part, "function_call", None)
        if function_call:
            item["function_call"] = {
                "name": getattr(function_call, "name", "") or "",
                "args": dict(getattr(function_call, "args", None) or {}),
                "id": getattr(function_call, "id", "") or "",
            }
        text = getattr(part, "text", None)
        if text:
            item["text"] = text
        function_response = getattr(part, "function_response", None)
        if function_response:
            item["function_response"] = {
                "name": getattr(function_response, "name", "") or "",
                "response": getattr(function_response, "response", None) or {},
                "id": getattr(function_response, "id", "") or "",
            }
        parts.append(item)
    return {
        "role": getattr(content, "role", None) or "model",
        "parts": parts,
        SDK_CONTENT_KEY: content,
    }


def _function_call_from_part(part: Any) -> FunctionCall | None:
    function_call = part.get("function_call") if isinstance(part, dict) else getattr(part, "function_call", None)
    if not function_call:
        return None
    if isinstance(function_call, dict):
        return FunctionCall(
            name=str(function_call.get("name") or ""),
            args=dict(function_call.get("args") or {}),
            id=str(function_call.get("id") or ""),
            thought_signature=part.get("thought_signature") if isinstance(part, dict) else getattr(part, "thought_signature", None),
        )
    return FunctionCall(
        name=str(getattr(function_call, "name", "") or ""),
        args=dict(getattr(function_call, "args", None) or {}),
        id=str(getattr(function_call, "id", "") or ""),
        thought_signature=getattr(part, "thought_signature", None),
    )


def function_calls_from_content(content: Any) -> list[FunctionCall]:
    parts = content.get("parts") if isinstance(content, dict) else getattr(content, "parts", None)
    calls: list[FunctionCall] = []
    for part in parts or []:
        call = _function_call_from_part(part)
        if call:
            calls.append(call)
    return calls


def _text_from_content(content: Any) -> str:
    parts = content.get("parts") if isinstance(content, dict) else getattr(content, "parts", None)
    texts: list[str] = []
    for part in parts or []:
        text = part.get("text") if isinstance(part, dict) else getattr(part, "text", None)
        if text:
            texts.append(str(text))
    return "".join(texts)


def _part_from_snapshot(part: dict[str, Any], types: Any) -> Any:
    kwargs: dict[str, Any] = {}
    if "thought_signature" in part and part["thought_signature"] is not None:
        kwargs["thought_signature"] = part["thought_signature"]
    if part.get("thought"):
        kwargs["thought"] = part["thought"]
    if "function_call" in part:
        call = part["function_call"] or {}
        call_kwargs: dict[str, Any] = {
            "name": call.get("name") or "",
            "args": call.get("args") or {},
        }
        if call.get("id"):
            call_kwargs["id"] = call["id"]
        kwargs["function_call"] = types.FunctionCall(**call_kwargs)
    if "text" in part and part["text"] is not None:
        kwargs["text"] = part["text"]
    if "function_response" in part:
        payload = part["function_response"] or {}
        response_kwargs: dict[str, Any] = {
            "name": payload.get("name") or "",
            "response": payload.get("response") or {},
        }
        if payload.get("id"):
            response_kwargs["id"] = payload["id"]
        kwargs["function_response"] = types.FunctionResponse(**response_kwargs)
    return types.Part(**kwargs)


def contents_for_sdk(contents: list[Any]) -> list[Any]:
    """Send original model content when present; otherwise rebuild every part field."""
    from google.genai import types

    converted = []
    for message in contents:
        if hasattr(message, "parts") and not isinstance(message, dict):
            converted.append(message)
            continue
        if isinstance(message, dict) and message.get(SDK_CONTENT_KEY) is not None:
            converted.append(message[SDK_CONTENT_KEY])
            continue
        payload = message if isinstance(message, dict) else {"role": "user", "parts": []}
        parts = [_part_from_snapshot(part, types) for part in payload.get("parts") or []]
        converted.append(types.Content(role=payload.get("role") or "user", parts=parts))
    return converted


class SequenceModel:
    """Deterministic stand-in used by tests. Never calls a live API."""

    def __init__(self, turns: list[ModelTurn]):
        self.turns = list(turns)
        self.calls = 0
        self.received: list[list[Any]] = []

    def generate(self, contents: list[Any]) -> ModelTurn:
        self.received.append(deepcopy(contents))
        self.calls += 1
        if not self.turns:
            return ModelTurn(text='{"status":"needs_human_review","summary":"No further model turns"}')
        turn = self.turns.pop(0)
        if turn.model_content is None:
            turn.model_content = default_model_content(turn)
        return turn


def grounded_search(query: str) -> dict[str, Any]:
    """Gemini Google Search grounding. Used only from the search_external_sources tool."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=(
            "Corroborate this private-markets entity or background term in 2-4 short facts. "
            f"Do not invent banking details. Query: {query}"
        ),
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.1,
        ),
    )
    citations: list[dict[str, str]] = []
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        meta = getattr(candidates[0], "grounding_metadata", None)
        chunks = getattr(meta, "grounding_chunks", None) or []
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            if web is None:
                continue
            citations.append(
                {
                    "title": getattr(web, "title", "") or "",
                    "uri": getattr(web, "uri", "") or "",
                    "snippet": "",
                }
            )
    return {
        "results": [{"text": getattr(response, "text", "") or ""}],
        "grounding_citations": citations,
    }


class GeminiModel:
    def generate(self, contents: list[Any]) -> ModelTurn:
        from google import genai
        from google.genai import types

        from agent.schemas import FUNCTION_DECLARATIONS, SYSTEM_INSTRUCTION

        declarations = [
            types.FunctionDeclaration(
                name=item["name"],
                description=item["description"],
                parameters=item["parameters"],
            )
            for item in FUNCTION_DECLARATIONS
        ]
        client = genai.Client(api_key=settings.gemini_api_key)
        converted = contents_for_sdk(contents)
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=converted,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=[types.Tool(function_declarations=declarations)],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                temperature=0.2,
            ),
        )
        model_content: dict[str, Any] | None = None
        candidates = getattr(response, "candidates", None) or []
        if candidates and getattr(candidates[0], "content", None):
            model_content = snapshot_model_content(candidates[0].content)
        calls = function_calls_from_content(model_content) if model_content else []
        text = _text_from_content(model_content) if model_content else ""
        if not text:
            text = getattr(response, "text", None) or ""
        return ModelTurn(function_calls=calls, text=text, model_content=model_content)
