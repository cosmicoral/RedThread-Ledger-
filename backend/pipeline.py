"""End-to-end statement processing.

Stages:
1. Extract statement transactions
2. Identify legal entity and bank account
3. Resolve sender or beneficiary
4. Match project codes, deals and positions
5. Classify the transaction
6. Generate and validate double-entry journal lines
"""

from pathlib import Path

from classification import classify_transaction
from extraction import extract_transactions
from journal import generate_journal_lines
from matching import match_transaction
from models import ReviewStatus, TransactionResult
from validation import validate_result


def process_statement(pdf_path: Path, reference_data: dict) -> list[TransactionResult]:
    extracted = extract_transactions(pdf_path)
    results: list[TransactionResult] = []

    for row in extracted:
        matched = match_transaction(row, reference_data)
        classified = classify_transaction(matched)
        with_journal = generate_journal_lines(classified, reference_data)
        results.append(validate_result(with_journal))

    return results


def review_queue(results: list[TransactionResult]) -> dict[str, list[TransactionResult]]:
    ready = [item for item in results if item.status == ReviewStatus.READY_TO_POST]
    review = [item for item in results if item.status == ReviewStatus.NEEDS_REVIEW]
    return {"ready_to_post": ready, "needs_review": review}
