from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from settings import settings


@dataclass
class FunctionCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelTurn:
    function_calls: list[FunctionCall] = field(default_factory=list)
    text: str = ""
    citations: list[dict[str, str]] = field(default_factory=list)


class AgentModel(Protocol):
    def generate(self, contents: list[dict[str, Any]]) -> ModelTurn:
        ...


class SequenceModel:
    """Deterministic stand-in used by tests. Never calls a live API."""

    def __init__(self, turns: list[ModelTurn]):
        self.turns = list(turns)
        self.calls = 0

    def generate(self, contents: list[dict[str, Any]]) -> ModelTurn:
        del contents
        self.calls += 1
        if not self.turns:
            return ModelTurn(text='{"status":"needs_human_review","summary":"No further model turns"}')
        return self.turns.pop(0)


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
    def generate(self, contents: list[dict[str, Any]]) -> ModelTurn:
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
        converted = []
        for message in contents:
            parts = []
            for part in message.get("parts", []):
                if "text" in part:
                    parts.append(types.Part.from_text(text=part["text"]))
                elif "function_call" in part:
                    call = part["function_call"]
                    parts.append(
                        types.Part.from_function_call(
                            name=call["name"],
                            args=call.get("args") or {},
                        )
                    )
                elif "function_response" in part:
                    payload = part["function_response"]
                    parts.append(
                        types.Part.from_function_response(
                            name=payload["name"],
                            response=payload["response"],
                        )
                    )
            converted.append(types.Content(role=message["role"], parts=parts))

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
        calls: list[FunctionCall] = []
        text = getattr(response, "text", None) or ""
        candidates = getattr(response, "candidates", None) or []
        if candidates and getattr(candidates[0], "content", None):
            for part in candidates[0].content.parts or []:
                function_call = getattr(part, "function_call", None)
                if function_call:
                    calls.append(
                        FunctionCall(
                            name=function_call.name,
                            args=dict(function_call.args or {}),
                        )
                    )
                elif getattr(part, "text", None):
                    text = part.text
        return ModelTurn(function_calls=calls, text=text)
