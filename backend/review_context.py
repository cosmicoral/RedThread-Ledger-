"""Deterministic, review-oriented metadata derived from pipeline output.

These fields explain and prioritize existing results. They do not change the
classification, journal, validation status, or accounting decision.
"""

from collections import defaultdict

from models import ExceptionReason, ReviewStatus, SourceSnapshot, TransactionResult


def _candidate_gap(item: TransactionResult) -> float | None:
    """Smallest leading-score gap among candidates for the same target field."""
    by_field: dict[str, list[float]] = defaultdict(list)
    for candidate in item.candidates:
        by_field[candidate.field or "unknown"].append(candidate.score)
    gaps: list[float] = []
    for scores in by_field.values():
        ranked = sorted(scores, reverse=True)
        if len(ranked) > 1:
            gaps.append(ranked[0] - ranked[1])
    return min(gaps) if gaps else None


def _issue_type(item: TransactionResult) -> str:
    reasons = set(item.exception_reasons)
    if reasons & {ExceptionReason.MISSING_COUNTERPARTY, ExceptionReason.AMBIGUOUS_COUNTERPARTY}:
        return "counterparty"
    if ExceptionReason.CLASSIFICATION_REVIEW in reasons:
        return "classification"
    if reasons & {ExceptionReason.MISSING_PROJECT, ExceptionReason.MISSING_POSITION}:
        return "project"
    if reasons & {ExceptionReason.IMPLAUSIBLE_BANK_CHARGE, ExceptionReason.VALIDATION_FAILURE}:
        return "amount"
    return "other"


def _uses_suspense(item: TransactionResult) -> bool:
    return any(
        "suspense" in f"{line.account} {line.transaction_type}".lower()
        for line in item.journal_lines
    )


def _unresolved(item: TransactionResult) -> bool:
    reasons = set(item.exception_reasons)
    if not item.classification or item.classification == "Review":
        return True
    if reasons & {ExceptionReason.MISSING_COUNTERPARTY, ExceptionReason.AMBIGUOUS_COUNTERPARTY}:
        return not item.counterparty
    if ExceptionReason.MISSING_PROJECT in reasons:
        return not item.project_code
    if ExceptionReason.MISSING_POSITION in reasons:
        return not item.position
    return False


def _match_reasons(item: TransactionResult) -> list[str]:
    reasons: list[str] = []
    for candidate in item.candidates:
        if not candidate.chosen:
            continue
        field = candidate.field or "reference"
        reasons.append(
            f"Chosen {field} match from {candidate.sheet} (score {candidate.score:.2f})"
        )
    return reasons


def _cash_direction(item: TransactionResult) -> str:
    if item.amount is not None:
        if item.amount > 0:
            return "inflow"
        if item.amount < 0:
            return "outflow"
    cash_types = " ".join(line.transaction_type.lower() for line in item.journal_lines)
    if "cash - received" in cash_types:
        return "inflow"
    if "cash - disbursed" in cash_types:
        return "outflow"
    return "unknown"


def enrich_review_context(results: list[TransactionResult]) -> list[TransactionResult]:
    """Populate review metadata after the complete review population is known."""
    review_amounts = sorted(
        abs(float(item.amount))
        for item in results
        if item.status == ReviewStatus.NEEDS_REVIEW and item.amount not in {None, 0}
    )
    large_threshold = (
        review_amounts[min(len(review_amounts) - 1, int(len(review_amounts) * 0.8))]
        if review_amounts
        else float("inf")
    )

    for item in results:
        item.issue_type = _issue_type(item)
        item.suspense_flag = _uses_suspense(item)
        gap = _candidate_gap(item)
        unresolved = _unresolved(item)
        missing_evidence = ExceptionReason.MISSING_EVIDENCE in item.exception_reasons
        unusually_large = item.amount is not None and abs(float(item.amount)) >= large_threshold

        if item.suspense_flag:
            item.issue_subtype = "suspense"
        elif missing_evidence:
            item.issue_subtype = "missing_evidence"
        elif gap is not None and gap <= 0.03:
            item.issue_subtype = "close_candidates"
        elif item.confidence < 0.65:
            item.issue_subtype = "low_confidence"
        elif unresolved:
            item.issue_subtype = "unresolved"
        else:
            item.issue_subtype = None

        if item.status == ReviewStatus.READY_TO_POST:
            item.attention_level = "low"
        elif missing_evidence or item.suspense_flag or unresolved or item.confidence < 0.60 or (gap is not None and gap <= 0.03):
            item.attention_level = "high"
        elif item.confidence < 0.80 or (gap is not None and gap < 0.10) or unusually_large:
            item.attention_level = "medium"
        else:
            item.attention_level = "low"

        item.cash_direction = _cash_direction(item)
        item.match_reasons = _match_reasons(item)
        item.source_snapshot = SourceSnapshot(
            document_name=item.evidence.document_name,
            page=item.evidence.page,
            raw_description=item.evidence.narrative,
            reference=item.evidence.bank_reference or item.evidence.customer_reference,
            account_number=item.evidence.account_number,
            amount=item.amount,
            currency=item.currency,
        )
    return results
