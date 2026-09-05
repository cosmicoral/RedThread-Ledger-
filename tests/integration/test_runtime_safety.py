from classification import is_interest_narrative, strong_fee_semantics
from models import ReviewStatus
from runtime import process_all


def test_official_pack_ids_are_unique_and_journals_stay_balanced() -> None:
    results = process_all()
    ids = [item.transaction_id for item in results]
    assert len(results) == 100
    assert len(set(ids)) == 100
    assert all(item.transaction_id for item in results)

    for item in results:
        debit = round(sum(line.debit for line in item.journal_lines), 2)
        credit = round(sum(line.credit for line in item.journal_lines), 2)
        assert len(item.journal_lines) == 2
        assert debit == credit


def test_unsupported_high_value_rows_are_not_ready_to_post() -> None:
    results = process_all()
    ready = [item for item in results if item.status == ReviewStatus.READY_TO_POST]
    review = [item for item in results if item.status == ReviewStatus.NEEDS_REVIEW]
    assert len(ready) + len(review) == 100

    unsupported_ready = []
    for item in ready:
        narrative = item.evidence.narrative or ""
        fee = strong_fee_semantics(narrative, item.evidence.trn_type or "")
        interest = is_interest_narrative(narrative)
        supported = bool(
            item.counterparty
            or item.related_party
            or item.classification == "Internal"
            or interest
            or fee
        )
        if not supported or (
            any(line.transaction_type == "Expense - Bank Charges" for line in item.journal_lines)
            and not fee
        ):
            unsupported_ready.append(item.transaction_id)
    assert unsupported_ready == []

    waived = [
        item
        for item in results
        if "CHARGE WAIVED" in (item.evidence.narrative or "").upper()
        and item.classification in {"Other", "Review"}
        and not item.counterparty
        and not item.project_code
    ]
    assert waived
    assert all(item.status == ReviewStatus.NEEDS_REVIEW for item in waived)
    assert all(
        any(reason.value == "implausible_bank_charge" for reason in item.exception_reasons)
        for item in waived
    )
