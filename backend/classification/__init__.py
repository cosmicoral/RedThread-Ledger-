from __future__ import annotations

from models import TransactionResult

INVESTMENT_HINTS = (
    "PROJECT",
    "PURCHASE",
    " ACQ ",
    "ACQ ",
    "EQUITY",
    "LOAN",
    "INVESTMENT",
    "CONTRIB",
)

STRONG_FEE_MARKERS = ("COMMISSION", "CHARGES FOR", "BANK FEE", "BANK CHARGES")
WEAK_FEE_MARKERS = ("WAIVED", "WAIVER", "REBATE", "REFUND", "REVERSAL")
# Statement bank fees/commissions are cents to tens of units. A four-figure
# "fee" without other support is treated as implausible, not posted.
PLAUSIBLE_BANK_CHARGE_ABS_MAX = 1_000.0


def weak_fee_semantics(narrative: str) -> bool:
    text = (narrative or "").upper()
    return any(marker in text for marker in WEAK_FEE_MARKERS)


def strong_fee_semantics(narrative: str, trn_type: str = "") -> bool:
    """True only for explicit fee language. CHG type or WAIVED is not enough."""
    del trn_type
    text = (narrative or "").upper()
    if weak_fee_semantics(text):
        return False
    return any(marker in text for marker in STRONG_FEE_MARKERS)


def is_interest_narrative(narrative: str) -> bool:
    text = (narrative or "").upper().strip()
    return "CREDIT INTEREST" in text or text == "INTEREST"


def implausible_bank_charge(result: TransactionResult) -> bool:
    """Hold fee-like or default bank-charge postings that lack safe semantics."""
    narrative = result.evidence.narrative or ""
    amount = abs(float(result.amount or 0))
    if is_interest_narrative(narrative):
        return False
    if result.classification == "Internal":
        return False
    if strong_fee_semantics(narrative, result.evidence.trn_type or ""):
        return amount > PLAUSIBLE_BANK_CHARGE_ABS_MAX
    posted_as_fee = (result.project_code or "") == "OH - Bank Fees" or (
        result.transaction_type or ""
    ) == "Expense - Bank Charges"
    if posted_as_fee:
        return True
    if weak_fee_semantics(narrative) and result.classification in {None, "", "Other", "Review"}:
        if result.counterparty or result.project_code:
            return False
        return True
    return result.classification == "Other"


def classify_transaction(result: TransactionResult) -> TransactionResult:
    narrative = (result.evidence.narrative or "").upper()
    notes: list[str] = []

    if strong_fee_semantics(narrative, result.evidence.trn_type or ""):
        amount = abs(float(result.amount or 0))
        if amount > PLAUSIBLE_BANK_CHARGE_ABS_MAX:
            result.classification = "Review"
            notes.append("Bank-charge amount is outside a plausible fee range")
            result.notes = "; ".join(filter(None, [result.notes, *notes]))
            return result
        result.classification = "Other"
        result.project_code = result.project_code or "OH - Bank Fees"
        return result

    if is_interest_narrative(narrative):
        result.classification = "Other"
        result.project_code = result.project_code or "OH - Interest Income"
        return result

    if "INTERNAL FX" in narrative or "INTERNAL TRANSFER" in narrative:
        result.classification = "Internal"
        return result

    investment_like = any(hint in f" {narrative} " for hint in INVESTMENT_HINTS)
    if result.pulled_project or result.equity_loan:
        investment_like = True

    if investment_like and (result.counterparty is None or result.position is None):
        result.classification = "Review"
        notes.append("Investment-like row is missing a unique counterparty or position")
        result.notes = "; ".join(filter(None, [result.notes, *notes]))
        return result

    if investment_like and result.related_party and result.legal_entity:
        if "PMT FRM" in narrative or "PAYMENT FROM" in narrative or "TO NI " in narrative:
            result.classification = "Investment Transfer"
        else:
            result.classification = "Investment"
        return result

    if investment_like:
        result.classification = "Investment"
        return result

    if result.related_party:
        result.classification = "Related Party"
        return result

    if result.counterparty:
        vendor_hit = any(
            item.chosen and item.sheet == "Vendor Master List" for item in result.candidates
        )
        investor_hit = any(
            item.chosen and item.sheet == "Investor Master List" for item in result.candidates
        )
        if investor_hit:
            result.classification = "Investor"
        elif vendor_hit:
            result.classification = "Vendor"
        else:
            result.classification = "Related Party"
        return result

    result.classification = "Review"
    if weak_fee_semantics(narrative):
        notes.append("Weak fee language is not enough to post a bank charge")
    else:
        notes.append("No supported classification; do not invent a bank-charge posting")
    result.notes = "; ".join(filter(None, [result.notes, *notes]))
    return result
