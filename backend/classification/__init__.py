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


def classify_transaction(result: TransactionResult) -> TransactionResult:
    narrative = (result.evidence.narrative or "").upper()
    notes: list[str] = []

    if any(token in narrative for token in ("COMMISSION", "CHARGES FOR", "BANK FEE")) or (
        result.evidence.trn_type or ""
    ).endswith("CHG"):
        result.classification = "Other"
        result.project_code = result.project_code or "OH - Bank Fees"
        return result

    if "CREDIT INTEREST" in narrative or "INTEREST" == narrative.strip():
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

    result.classification = "Other"
    return result
