from pathlib import Path

from classification import classify_transaction
from journal import generate_journal_lines
from matching import match_transaction
from reference.loader import load_reference_data
from validation import validate_result

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "reference"


def _refs() -> dict:
    return load_reference_data(FIXTURE_DIR)


def _row(**overrides: object) -> dict:
    base = {
        "transaction_id": "tx-fee",
        "document_name": "statement.pdf",
        "page": 1,
        "account_name": "NI ABF II SCSP",
        "account_number": "240-149813-030",
        "currency": "EUR",
        "bank_reference": "NONREF",
        "date": "2026-03-31",
        "amount": -0.44,
        "narrative": "CHARGES FOR 2, OUTWARD SEPA PAYMENT",
    }
    base.update(overrides)
    return base


def _run(row: dict):
    refs = _refs()
    matched = match_transaction(row, refs)
    classified = classify_transaction(matched)
    journaled = generate_journal_lines(classified, refs)
    return validate_result(journaled)


def test_bank_fee_produces_two_balanced_lines() -> None:
    result = _run(_row())
    assert result.classification == "Other"
    assert len(result.journal_lines) == 2
    assert round(sum(line.debit for line in result.journal_lines), 2) == 0.44
    assert round(sum(line.credit for line in result.journal_lines), 2) == 0.44
    assert result.status.value == "ready_to_post"
    assert any(line.transaction_type == "Expense - Bank Charges" for line in result.journal_lines)
    assert any(line.transaction_type == "Cash - Disbursed - EUR" for line in result.journal_lines)


def test_cephalus_investment_transfer_is_balanced() -> None:
    result = _run(
        _row(
            transaction_id="tx-ceph",
            bank_reference="10716RS62GWQ",
            amount=-301908.70,
            narrative=(
                "NI ABF I SCSP, PMT FRM NI ABF II SCSP TO NI ABF I, SCSP FOR PURCHASE "
                "100PER OF ACC INT, IN CEPHALUS BIOGAS 001 LTD PREMIUM, ACCRUED INTEREST PROJECT CEPHALUS"
            ),
        )
    )
    assert result.classification == "Investment Transfer"
    assert result.position is not None
    assert len(result.journal_lines) == 2
    assert round(sum(line.debit for line in result.journal_lines), 2) == 301908.70


def test_single_line_is_validation_failure() -> None:
    refs = _refs()
    matched = match_transaction(_row(), refs)
    classified = classify_transaction(matched)
    classified.journal_lines = classified.journal_lines[:1]
    result = validate_result(classified)
    assert result.status.value == "needs_review"
    assert any(reason.value == "validation_failure" for reason in result.exception_reasons)
