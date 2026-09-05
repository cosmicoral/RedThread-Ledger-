from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Callable

from agent.client import AgentModel, GeminiModel, ModelTurn, grounded_search
from agent.models import (
    AgentReviewResult,
    AgentStatus,
    AgentStep,
    Citation,
    ProposedFields,
    ProposedJournalLine,
    ToolTraceItem,
    ValidationResult,
)
from agent.tools import dispatch_tool, require_needs_review, validate_proposed_journal
from models import TransactionResult
from runtime import get_transaction
from settings import settings

def _fallback(transaction: TransactionResult, reason: str, trace: list[ToolTraceItem] | None = None) -> AgentReviewResult:
    return AgentReviewResult(
        transaction_id=transaction.transaction_id,
        status=AgentStatus.NEEDS_HUMAN_REVIEW,
        summary="Agent review is unavailable. The deterministic Needs-review result is unchanged.",
        unresolved_questions=[reason],
        tool_trace=trace or [],
        fallback=True,
        fallback_reason=reason,
        original_status=transaction.status.value,
        human_approval_required=True,
        confidence=0.0,
    )


def _summarize_tool_result(name: str, payload: dict[str, Any]) -> str:
    if name == "get_transaction_evidence":
        return f"Evidence {payload.get('document_name')} p.{payload.get('page')}"
    if name == "search_internal_master_data":
        count = len(payload.get("candidates") or [])
        return f"{count} internal candidate(s)"
    if name == "search_external_sources":
        count = len(payload.get("citations") or [])
        return f"{count} external citation(s)"
    if name == "validate_proposed_journal":
        return "journal valid" if payload.get("valid") else "journal invalid"
    if name == "escalate_to_human":
        return str(payload.get("reason") or "escalated")
    return name


def _parse_final_text(text: str) -> dict[str, Any]:
    blob = (text or "").strip()
    if not blob:
        return {}
    if blob.startswith("```"):
        blob = re.sub(r"^```(?:json)?\s*", "", blob)
        blob = re.sub(r"\s*```$", "", blob)
    try:
        parsed = json.loads(blob)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", blob, re.S)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _coerce_status(value: str | None, validation: ValidationResult, escalated: bool) -> AgentStatus:
    if escalated:
        return AgentStatus.NEEDS_HUMAN_REVIEW
    # A model that asks to post is treated as a suggestion, never a post.
    if value == "ready_to_post":
        value = AgentStatus.AGENT_SUGGESTED.value
    if not validation.valid:
        return AgentStatus.NEEDS_HUMAN_REVIEW
    if value == AgentStatus.AGENT_SUGGESTED.value:
        return AgentStatus.AGENT_SUGGESTED
    return AgentStatus.NEEDS_HUMAN_REVIEW


def _build_result(
    transaction: TransactionResult,
    *,
    parsed: dict[str, Any],
    trace: list[ToolTraceItem],
    citations: list[Citation],
    internal: list[dict[str, Any]],
    escalated: bool,
    escalate_reason: str = "",
) -> AgentReviewResult:
    lines = [
        ProposedJournalLine.model_validate(row)
        for row in parsed.get("proposed_journal_lines") or []
        if isinstance(row, dict)
    ]
    validation = ValidationResult.model_validate(
        validate_proposed_journal(
            {
                "currency": transaction.currency,
                "classification": (parsed.get("proposed_fields") or {}).get("classification")
                if isinstance(parsed.get("proposed_fields"), dict)
                else parsed.get("classification"),
                "lines": [line.model_dump() for line in lines],
            },
            transaction,
        )
    )
    fields = parsed.get("proposed_fields") if isinstance(parsed.get("proposed_fields"), dict) else {}
    status = _coerce_status(str(parsed.get("status") or ""), validation, escalated)
    questions = [str(item) for item in parsed.get("unresolved_questions") or []]
    if escalate_reason:
        questions.append(escalate_reason)
    if not validation.valid:
        questions.extend(validation.errors)
    summary = str(parsed.get("summary") or escalate_reason or "Agent could not form a supported proposal.")
    try:
        confidence = float(parsed.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    return AgentReviewResult(
        transaction_id=transaction.transaction_id,
        status=status,
        summary=summary,
        proposed_fields=ProposedFields.model_validate(fields),
        proposed_journal_lines=lines,
        confidence=max(0.0, min(1.0, confidence)),
        unresolved_questions=questions,
        internal_evidence=internal,
        external_citations=citations,
        tool_trace=trace,
        deterministic_validation=validation,
        original_status=transaction.status.value,
        human_approval_required=True,
    )


def _loop(
    transaction: TransactionResult,
    model: AgentModel,
    search_fn: Callable[[str], dict[str, Any]] | None,
) -> AgentReviewResult:
    contents: list[dict[str, Any]] = [
        {
            "role": "user",
            "parts": [
                {
                    "text": (
                        f"Investigate Needs-review transaction {transaction.transaction_id}. "
                        "Start with get_transaction_evidence. Do not change the original deterministic result."
                    )
                }
            ],
        }
    ]
    trace: list[ToolTraceItem] = []
    citations: list[Citation] = []
    internal: list[dict[str, Any]] = []
    escalated = False
    escalate_reason = ""
    last_text = ""
    max_rounds = max(1, int(settings.agent_max_tool_rounds))

    for _ in range(max_rounds):
        turn: ModelTurn = model.generate(contents)
        last_text = turn.text
        if not turn.function_calls:
            break
        responses = []
        for call in turn.function_calls:
            payload = dispatch_tool(
                call.name,
                call.args,
                transaction=transaction,
                search_fn=search_fn,
            )
            step = AgentStep(TOOL_STEP_SAFE(call.name))
            trace.append(
                ToolTraceItem(
                    step=step,
                    tool=call.name,
                    arguments=_safe_args(call.args),
                    result_summary=_summarize_tool_result(call.name, payload),
                    ok="error" not in payload,
                )
            )
            if call.name == "search_internal_master_data":
                internal.extend(payload.get("candidates") or [])
            if call.name == "search_external_sources":
                for row in payload.get("citations") or []:
                    citations.append(Citation.model_validate(row))
            if call.name == "escalate_to_human" or payload.get("escalated"):
                escalated = True
                escalate_reason = str(payload.get("reason") or "Escalated to a human reviewer")
            responses.append(
                {
                    "function_response": {
                        "name": call.name,
                        "response": payload,
                    }
                }
            )
        contents.append(
            {
                "role": "model",
                "parts": [
                    {"function_call": {"name": call.name, "args": call.args}}
                    for call in turn.function_calls
                ],
            }
        )
        contents.append({"role": "user", "parts": responses})
        if escalated:
            break

    parsed = _parse_final_text(last_text)
    if escalated and not parsed:
        parsed = {
            "status": AgentStatus.NEEDS_HUMAN_REVIEW.value,
            "summary": escalate_reason or "Escalated to a human reviewer",
            "unresolved_questions": [escalate_reason],
        }
    if not parsed and not escalated:
        parsed = {
            "status": AgentStatus.NEEDS_HUMAN_REVIEW.value,
            "summary": "The agent reached the tool-round limit without a supported recommendation.",
        }
    return _build_result(
        transaction,
        parsed=parsed,
        trace=trace,
        citations=citations,
        internal=internal,
        escalated=escalated,
        escalate_reason=escalate_reason,
    )


def TOOL_STEP_SAFE(name: str) -> str:
    from agent.tools import TOOL_STEP

    return TOOL_STEP.get(name, AgentStep.RECOMMENDATION.value)


def _safe_args(arguments: dict[str, Any]) -> dict[str, Any]:
    cleaned = {}
    for key, value in arguments.items():
        if key == "proposal" and isinstance(value, dict):
            cleaned[key] = {"keys": sorted(value.keys())}
        else:
            cleaned[key] = value
    return cleaned


def run_agent_review(
    transaction_id: str,
    *,
    model: AgentModel | None = None,
    search_fn: Callable[[str], dict[str, Any]] | None = None,
) -> AgentReviewResult:
    item = get_transaction(transaction_id)
    if item is None:
        return AgentReviewResult(
            transaction_id=transaction_id,
            status=AgentStatus.NEEDS_HUMAN_REVIEW,
            summary="Transaction not found",
            fallback=True,
            fallback_reason="transaction_not_found",
            human_approval_required=True,
        )
    blocked = require_needs_review(item)
    if blocked:
        return AgentReviewResult(
            transaction_id=item.transaction_id,
            status=AgentStatus.NEEDS_HUMAN_REVIEW,
            summary=blocked,
            fallback=True,
            fallback_reason=blocked,
            original_status=item.status.value,
            human_approval_required=True,
        )
    if not settings.agent_enabled:
        return _fallback(item, "AGENT_ENABLED is false")
    if model is None and not settings.gemini_api_key:
        return _fallback(item, "GEMINI_API_KEY is not configured")

    active_model = model or GeminiModel()
    active_search = search_fn
    if active_search is None and model is None and settings.gemini_api_key:
        active_search = grounded_search

    def _run() -> AgentReviewResult:
        return _loop(item, active_model, active_search)

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run)
            return future.result(timeout=settings.agent_timeout_seconds)
    except FuturesTimeout:
        return _fallback(item, f"Timed out after {settings.agent_timeout_seconds}s")
    except Exception as exc:  # noqa: BLE001 - convert provider failures into a reviewable fallback
        return _fallback(item, f"Gemini unavailable: {exc.__class__.__name__}")
