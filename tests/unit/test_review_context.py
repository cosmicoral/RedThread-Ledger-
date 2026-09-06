from models import (
    ExceptionReason,
    JournalLine,
    MatchCandidate,
    ReviewStatus,
    SourceEvidence,
    TransactionResult,
)
from review_context import enrich_review_context


def _result(**overrides) -> TransactionResult:
    values = {
        "transaction_id": "demo-1",
        "amount": -100.0,
        "currency": "EUR",
        "classification": "Review",
        "confidence": 0.92,
        "status": ReviewStatus.NEEDS_REVIEW,
        "exception_reasons": [ExceptionReason.CLASSIFICATION_REVIEW],
        "evidence": SourceEvidence(
            document_name="statement.pdf",
            page=3,
            narrative="PAYMENT DESCRIPTION",
            bank_reference="REF-1",
            account_number="1234",
        ),
    }
    values.update(overrides)
    return TransactionResult(**values)


def test_tied_same_field_candidates_are_close_candidates() -> None:
    item = _result(candidates=[
        MatchCandidate(sheet="Vendor Master List", key="a", label="A", score=0.92, field="vendor"),
        MatchCandidate(sheet="Vendor Master List", key="b", label="B", score=0.92, field="vendor"),
        MatchCandidate(sheet="Vendor Master List", key="c", label="C", score=0.88, field="vendor"),
    ])
    enrich_review_context([item])
    assert item.issue_type == "classification"
    assert item.issue_subtype == "close_candidates"
    assert item.attention_level == "high"
    assert item.cash_direction == "outflow"


def test_suspense_has_subtype_priority_and_snapshot_is_real_data() -> None:
    item = _result(
        journal_lines=[JournalLine(account="39990", transaction_type="Suspense (debit)")],
    )
    enrich_review_context([item])
    assert item.suspense_flag is True
    assert item.issue_subtype == "suspense"
    assert item.source_snapshot is not None
    assert item.source_snapshot.raw_description == item.evidence.narrative
    assert item.source_snapshot.reference == "REF-1"


def test_match_reasons_only_include_chosen_candidates() -> None:
    item = _result(candidates=[
        MatchCandidate(sheet="Legal Entity Master List", key="a", label="Fund A", score=0.91, chosen=True, field="legal_entity"),
        MatchCandidate(sheet="Legal Entity Master List", key="b", label="Fund B", score=0.90, chosen=False, field="legal_entity"),
    ])
    enrich_review_context([item])
    assert item.match_reasons == [
        "Chosen legal_entity match from Legal Entity Master List (score 0.91)"
    ]
