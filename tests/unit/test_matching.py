from pathlib import Path

from matching import match_transaction, pull_counterparty
from reference.loader import load_reference_data

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "reference"


def _refs() -> dict:
    return load_reference_data(FIXTURE_DIR)


def _row(**overrides: object) -> dict:
    base = {
        "transaction_id": "tx-1",
        "document_name": "20260331_NI_A_B__FUND_II_CALDER_EUR_8102.pdf",
        "page": 1,
        "account_name": "NI ABF II SCSP",
        "account_number": "240-149813-030",
        "currency": "EUR",
        "bank_reference": "10716RS62GWQ",
        "date": "2026-03-31",
        "amount": -301908.70,
        "narrative": (
            "NI ABF I SCSP, PMT FRM NI ABF II SCSP TO NI ABF I, SCSP FOR PURCHASE "
            "100PER OF ACC INT, IN CEPHALUS BIOGAS 001 LTD PREMIUM, ACCRUED INTEREST PROJECT CEPHALUS"
        ),
    }
    base.update(overrides)
    return base


def test_cephalus_path_resolves() -> None:
    result = match_transaction(_row(), _refs())
    assert result.legal_entity == "Nordvik Infrastructure Advanced Bioenergy Fund II SCSp"
    assert result.bank_account == "NI ABF II - Calder - EUR - 8102"
    assert result.pulled_project == "CEPHALUS"
    assert result.project_code == "Cephalus"
    assert result.counterparty == "NI ABF I SCSp"
    assert result.deal == "Cephalus Biogas 001 Limited - EUR"
    assert result.position == "Cephalus Biogas 001 Limited - EUR (Funding Loan)"


def test_interest_and_commission_do_not_invent_counterparty() -> None:
    refs = _refs()
    interest = match_transaction(_row(narrative="CREDIT INTEREST", amount=50.54), refs)
    commission = match_transaction(
        _row(narrative="COMMISSION DKK 44,84, 53520NL113KD", amount=-44.84), refs
    )
    assert interest.pulled_counterparty is None
    assert interest.counterparty is None
    assert commission.pulled_counterparty is None
    assert commission.counterparty is None


def test_vendor_name_is_pulled_from_trailing_clause() -> None:
    assert pull_counterparty("52443473437109-3528152584, TRENTBECK AUDIT LUXEMBOURG") == (
        "TRENTBECK AUDIT LUXEMBOURG"
    )
