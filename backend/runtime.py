from pathlib import Path

from pipeline import process_statement, review_queue
from reference.loader import load_reference_data
from models import TransactionResult
from settings import settings

_results: list[TransactionResult] = []
_agent_reviews: dict[str, object] = {}


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
    global _results, _agent_reviews
    _results = results
    _agent_reviews = {}
    return results


def store_agent_review(review: object) -> None:
    transaction_id = getattr(review, "transaction_id", None)
    if transaction_id:
        _agent_reviews[transaction_id] = review


def get_agent_review(transaction_id: str) -> object | None:
    return _agent_reviews.get(transaction_id)


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
