from enum import Enum

from pydantic import BaseModel, Field


class ReviewStatus(str, Enum):
    READY_TO_POST = "ready_to_post"
    NEEDS_REVIEW = "needs_review"


class ExceptionReason(str, Enum):
    MISSING_PROJECT = "missing_project"
    MISSING_COUNTERPARTY = "missing_counterparty"
    AMBIGUOUS_COUNTERPARTY = "ambiguous_counterparty"
    MISSING_POSITION = "missing_position"
    CLASSIFICATION_REVIEW = "classification_review"
    IMPLAUSIBLE_BANK_CHARGE = "implausible_bank_charge"
    VALIDATION_FAILURE = "validation_failure"
    MISSING_EVIDENCE = "missing_evidence"


class SourceEvidence(BaseModel):
    document_name: str
    page: int | None = None
    bank_reference: str | None = None
    customer_reference: str | None = None
    trn_type: str | None = None
    narrative: str = ""
    account_name: str | None = None
    account_number: str | None = None


class MatchCandidate(BaseModel):
    sheet: str
    key: str
    label: str
    score: float
    chosen: bool = False
    field: str = ""


class JournalLine(BaseModel):
    account: str
    transaction_type: str = ""
    debit: float = 0.0
    credit: float = 0.0
    memo: str = ""
    allocation_rule: str = ""


class TransactionResult(BaseModel):
    transaction_id: str
    date: str | None = None
    currency: str | None = None
    amount: float | None = None
    bank_account: str | None = None
    legal_entity: str | None = None
    pulled_counterparty: str | None = None
    counterparty: str | None = None
    related_party: str | None = None
    pulled_project: str | None = None
    project_code: str | None = None
    equity_loan: str | None = None
    classification: str | None = None
    transaction_type: str | None = None
    cash_leg_type: str | None = None
    counterparty_leg_type: str | None = None
    deal: str | None = None
    position: str | None = None
    allocation_rule: str | None = None
    confidence: float = 0.0
    status: ReviewStatus = ReviewStatus.NEEDS_REVIEW
    exception_reasons: list[ExceptionReason] = Field(default_factory=list)
    evidence: SourceEvidence
    candidates: list[MatchCandidate] = Field(default_factory=list)
    journal_lines: list[JournalLine] = Field(default_factory=list)
    notes: str = ""
