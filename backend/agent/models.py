from enum import Enum

from pydantic import BaseModel, Field


class AgentStatus(str, Enum):
    AGENT_SUGGESTED = "agent_suggested"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


class AgentStep(str, Enum):
    EVIDENCE = "evidence"
    INTERNAL_LOOKUP = "internal_lookup"
    EXTERNAL_RESEARCH = "external_research"
    VALIDATION = "validation"
    RECOMMENDATION = "recommendation"


class ToolTraceItem(BaseModel):
    step: AgentStep
    tool: str
    arguments: dict = Field(default_factory=dict)
    result_summary: str = ""
    ok: bool = True


class ProposedFields(BaseModel):
    counterparty: str | None = None
    related_party: str | None = None
    project_code: str | None = None
    classification: str | None = None
    deal: str | None = None
    position: str | None = None
    equity_loan: str | None = None


class ProposedJournalLine(BaseModel):
    account: str = ""
    transaction_type: str = ""
    debit: float = 0.0
    credit: float = 0.0
    memo: str = ""


class ValidationResult(BaseModel):
    valid: bool = False
    errors: list[str] = Field(default_factory=list)
    checks: dict[str, bool] = Field(default_factory=dict)


class Citation(BaseModel):
    title: str = ""
    uri: str = ""
    snippet: str = ""


class AgentReviewResult(BaseModel):
    transaction_id: str
    status: AgentStatus = AgentStatus.NEEDS_HUMAN_REVIEW
    summary: str = ""
    proposed_fields: ProposedFields = Field(default_factory=ProposedFields)
    proposed_journal_lines: list[ProposedJournalLine] = Field(default_factory=list)
    confidence: float = 0.0
    unresolved_questions: list[str] = Field(default_factory=list)
    internal_evidence: list[dict] = Field(default_factory=list)
    external_citations: list[Citation] = Field(default_factory=list)
    tool_trace: list[ToolTraceItem] = Field(default_factory=list)
    deterministic_validation: ValidationResult = Field(default_factory=ValidationResult)
    fallback: bool = False
    fallback_reason: str = ""
    original_status: str = "needs_review"
    human_approval_required: bool = True
