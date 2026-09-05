from pathlib import Path

from pipeline import process_statement, review_queue
from reference.loader import load_reference_data
from models import TransactionResult
from settings import settings

_results: list[TransactionResult] = []


def process_all(
    statements_dir: str | Path | None = None,
    reference_dir: str | Path | None = None,
) -> list[TransactionResult]:
    refs = load_reference_data(reference_dir or settings.hackathon_reference_dir)
    results: list[TransactionResult] = []
    root = Path(statements_dir or settings.hackathon_statements_dir)
    if root.is_dir():
        for pdf in sorted(root.glob("*.pdf")):
            results.extend(process_statement(pdf, refs))
    global _results
    _results = results
    return results


def current_results() -> list[TransactionResult]:
    return list(_results)


def get_transaction(transaction_id: str) -> TransactionResult | None:
    for item in _results:
        if item.transaction_id == transaction_id:
            return item
    return None


def current_queue() -> dict[str, list[TransactionResult]]:
    return review_queue(_results)


def statement_path(name: str) -> Path | None:
    safe = Path(name).name
    path = Path(settings.hackathon_statements_dir) / safe
    if path.is_file() and path.suffix.lower() == ".pdf":
        return path
    return None
