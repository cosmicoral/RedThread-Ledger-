from classification import implausible_bank_charge
from models import ExceptionReason, ReviewStatus, TransactionResult

INVESTMENT_CLASSES = {"Investment", "Investment Transfer"}
COUNTERPARTY_CLASSES = {"Vendor", "Related Party", "Investor", "Investment Transfer", "Investment"}


def validate_result(result: TransactionResult) -> TransactionResult:
    """Apply deterministic checks: required fields, two lines, balanced books."""
    reasons: list[ExceptionReason] = []

    if len(result.journal_lines) != 2:
        reasons.append(ExceptionReason.VALIDATION_FAILURE)
    else:
        debit = sum(line.debit for line in result.journal_lines)
        credit = sum(line.credit for line in result.journal_lines)
        if round(debit - credit, 2) != 0:
            reasons.append(ExceptionReason.VALIDATION_FAILURE)

    if not result.evidence.document_name:
        reasons.append(ExceptionReason.MISSING_EVIDENCE)

    classification = result.classification or ""
    if implausible_bank_charge(result):
        reasons.append(ExceptionReason.IMPLAUSIBLE_BANK_CHARGE)
    if classification == "Review":
        reasons.append(ExceptionReason.CLASSIFICATION_REVIEW)

    if classification in INVESTMENT_CLASSES and not result.project_code:
        reasons.append(ExceptionReason.MISSING_PROJECT)
    if classification in INVESTMENT_CLASSES and not result.position:
        reasons.append(ExceptionReason.MISSING_POSITION)

    if classification in COUNTERPARTY_CLASSES and not result.counterparty:
        if any(item.field == "vendor" or item.field == "related_party" for item in result.candidates):
            reasons.append(ExceptionReason.AMBIGUOUS_COUNTERPARTY)
        else:
            reasons.append(ExceptionReason.MISSING_COUNTERPARTY)

    # unique preserve order
    deduped: list[ExceptionReason] = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    result.exception_reasons = deduped
    result.status = ReviewStatus.NEEDS_REVIEW if deduped else ReviewStatus.READY_TO_POST
    return result
