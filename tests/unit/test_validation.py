from models import JournalLine, SourceEvidence, TransactionResult
from validation import validate_result


def _result(lines: list[JournalLine]) -> TransactionResult:
    return TransactionResult(
        transaction_id="tx-1",
        evidence=SourceEvidence(document_name="statement.pdf", page=1),
        journal_lines=lines,
    )


def test_unbalanced_lines_need_review() -> None:
    result = validate_result(
        _result(
            [
                JournalLine(account="Cash", debit=100),
                JournalLine(account="Investment", credit=90),
            ]
        )
    )
    assert result.status.value == "needs_review"


def test_balanced_two_lines_are_ready() -> None:
    result = validate_result(
        _result(
            [
                JournalLine(account="Cash", debit=100),
                JournalLine(account="Investment", credit=100),
            ]
        )
    )
    assert result.status.value == "ready_to_post"
