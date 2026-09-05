from pathlib import Path

from extraction.parser import parse_statement_pages

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "statements"


def _pages() -> list[tuple[int, str]]:
    return [
        (1, (FIXTURES / "eur_8102_page1.txt").read_text()),
        (2, (FIXTURES / "eur_8102_page2.txt").read_text()),
    ]


def test_extracts_fee_and_cephalus_rows() -> None:
    rows = parse_statement_pages(_pages(), document_name="20260331_NI_A_B__FUND_II_CALDER_EUR_8102.pdf")
    by_ref = {row["bank_reference"]: row for row in rows}

    fee = next(row for row in rows if row["amount"] == -0.44)
    assert fee["bank_reference"] == "NONREF"
    assert fee["amount"] == -0.44
    assert fee["date"] == "2026-03-31"
    assert fee["currency"] == "EUR"
    assert fee["narrative"] == "CHARGES FOR 2, OUTWARD SEPA PAYMENT"
    assert fee["page"] == 1

    cephalus = by_ref["10716RS62GWQ"]
    assert cephalus["amount"] == -301908.70
    assert "PROJECT CEPHALUS" in cephalus["narrative"]
    assert cephalus["page"] == 1


def test_joins_wrapped_transaction_line() -> None:
    rows = parse_statement_pages(_pages(), document_name="statement.pdf")
    tren = next(row for row in rows if row["bank_reference"] == "YP03586039037340")
    assert tren["amount"] == -5085.23
    assert "TRENTBECK AUDIT LUXEMBOURG" in tren["narrative"]


def test_vertical_pypdf_layout() -> None:
    text = """
Account name
NI ABF II SCSP
Account number
240-149813-030
Currency
EUR
Bank reference
Customer reference
TRN type
Value date
Credit amount
Debit amount
Balance
Time
Post date
NONREF
NONREF
TFR-
31 Mar 2026
-0.44
20,088.32
17:46
31 Mar 2026
Narrative
CHARGES FOR 2, OUTWARD SEPA PAYMENT
10716RS62GWQ
CEPHALUS TRF
TFR-
31 Mar 2026
-301,908.70
20,088.76
11:01
31 Mar 2026
Narrative
NI ABF I SCSP PROJECT CEPHALUS
"""
    rows = parse_statement_pages([(1, text)], document_name="vertical.pdf")
    assert len(rows) == 2
    assert rows[0]["amount"] == -0.44
    assert rows[0]["narrative"] == "CHARGES FOR 2, OUTWARD SEPA PAYMENT"
    assert rows[1]["bank_reference"] == "10716RS62GWQ"
    assert "PROJECT CEPHALUS" in rows[1]["narrative"]


def test_second_page_number_and_interest() -> None:
    rows = parse_statement_pages(_pages(), document_name="statement.pdf")
    interest = next(row for row in rows if "CREDIT INTEREST" in row["narrative"])
    assert interest["page"] == 2
    assert interest["amount"] == 50.54
    assert interest["account_number"] == "240-149813-030"
