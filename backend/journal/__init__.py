from __future__ import annotations

from models import JournalLine, TransactionResult

COUNTERPARTY_LEGS = {
    ("Other", "fee"): ("Expense - Bank Charges", "43000.1"),
    ("Other", "interest"): ("Income - Bank Interest", "65000"),
    ("Internal", ""): ("Currency Correcting Credit", "39980"),
    ("Investment", "Equity"): ("Investments - Equity - Purchase", "12000"),
    ("Investment", "Loan"): ("Investments - Loan - Purchase", "11000"),
    ("Investment Transfer", ""): ("Payable - Third Party", "20500.5"),
    ("Related Party", ""): ("Payable - Related Party", "20500.1"),
    ("Vendor", ""): ("Accounts Payable", "20500.4"),
    ("Investor", ""): ("Receivable", "16100.1"),
    ("Review", ""): ("Suspense (debit)", "39990"),
}


def _coa_account(reference_data: dict, trans_type: str, fallback: str) -> str:
    for row in reference_data.get("CoA", []):
        if row.get("Trans Type") == trans_type and row.get("Account"):
            return row["Account"]
    return fallback


def _allocation(result: TransactionResult, reference_data: dict, side: str) -> str:
    project = result.project_code or ""
    korean = [
        row.get("Project") or row.get(list(row.keys())[-1], "")
        for row in reference_data.get("Korean and Taiwanese", [])
    ]
    if project and any(project.lower() == (item or "").lower() for item in korean):
        return "DAR: Deal"
    if side == "cash":
        return "Non Dominant"
    for row in reference_data.get("Allocation Rule", []):
        if row.get("Legal Entity") == result.legal_entity and row.get("Allocation Rule"):
            return row["Allocation Rule"]
    return "No Allocation"


def _counterparty_leg(result: TransactionResult) -> tuple[str, str]:
    narrative = (result.evidence.narrative or "").upper()
    if result.classification == "Other" and (
        "INTEREST" in narrative and "CHARGES" not in narrative and "COMMISSION" not in narrative
    ):
        return COUNTERPARTY_LEGS[("Other", "interest")]
    if result.classification == "Other":
        return COUNTERPARTY_LEGS[("Other", "fee")]
    if result.classification == "Investment":
        if result.equity_loan == "Equity":
            return COUNTERPARTY_LEGS[("Investment", "Equity")]
        return COUNTERPARTY_LEGS[("Investment", "Loan")]
    return COUNTERPARTY_LEGS.get((result.classification or "Review", ""), COUNTERPARTY_LEGS[("Review", "")])


def generate_journal_lines(
    result: TransactionResult, reference_data: dict | None = None
) -> TransactionResult:
    reference_data = reference_data or {}
    if result.amount is None:
        return result

    amount = round(abs(float(result.amount)), 2)
    currency = result.currency or ""
    outgoing = float(result.amount) < 0
    narrative = result.evidence.narrative

    if outgoing:
        cash_type = f"Cash - Disbursed - {currency}".strip()
    else:
        cash_type = f"Cash - Received - {currency}".strip()

    counterpart_type, counterpart_account = _counterparty_leg(result)
    cash_account = _coa_account(reference_data, "Cash - Disbursed" if outgoing else "Cash - Received", "10000")
    counterpart_account = _coa_account(reference_data, counterpart_type.split(" - ")[0] if False else counterpart_type, counterpart_account)

    cash_alloc = _allocation(result, reference_data, "cash")
    counterpart_alloc = _allocation(result, reference_data, "counterpart")

    if outgoing:
        cash_line = JournalLine(
            account=cash_account,
            transaction_type=cash_type,
            credit=amount,
            memo=narrative,
            allocation_rule=cash_alloc,
        )
        counterpart_line = JournalLine(
            account=counterpart_account,
            transaction_type=counterpart_type,
            debit=amount,
            memo=narrative,
            allocation_rule=counterpart_alloc,
        )
    else:
        cash_line = JournalLine(
            account=cash_account,
            transaction_type=cash_type,
            debit=amount,
            memo=narrative,
            allocation_rule=cash_alloc,
        )
        counterpart_line = JournalLine(
            account=counterpart_account,
            transaction_type=counterpart_type,
            credit=amount,
            memo=narrative,
            allocation_rule=counterpart_alloc,
        )

    result.cash_leg_type = cash_type
    result.counterparty_leg_type = counterpart_type
    result.transaction_type = counterpart_type
    result.allocation_rule = counterpart_alloc
    result.journal_lines = [counterpart_line, cash_line]
    return result
