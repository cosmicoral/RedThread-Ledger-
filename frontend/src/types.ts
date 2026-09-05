export type ReviewStatus = "ready_to_post" | "needs_review";

export type ExceptionReason =
  | "missing_project"
  | "missing_counterparty"
  | "ambiguous_counterparty"
  | "missing_position"
  | "classification_review"
  | "validation_failure"
  | "missing_evidence";

export type MatchCandidate = {
  sheet: string;
  key: string;
  label: string;
  score: number;
  chosen: boolean;
  field: string;
};

export type JournalLine = {
  account: string;
  transaction_type: string;
  debit: number;
  credit: number;
  memo: string;
  allocation_rule: string;
};

export type TransactionResult = {
  transaction_id: string;
  date: string | null;
  currency: string | null;
  amount: number | null;
  bank_account: string | null;
  legal_entity: string | null;
  pulled_counterparty: string | null;
  counterparty: string | null;
  related_party: string | null;
  pulled_project: string | null;
  project_code: string | null;
  equity_loan: string | null;
  classification: string | null;
  deal: string | null;
  position: string | null;
  confidence: number;
  status: ReviewStatus;
  exception_reasons: ExceptionReason[];
  evidence: {
    document_name: string;
    page: number | null;
    bank_reference: string | null;
    customer_reference: string | null;
    trn_type: string | null;
    narrative: string;
    account_name: string | null;
    account_number: string | null;
  };
  candidates: MatchCandidate[];
  journal_lines: JournalLine[];
  notes: string;
};

export type QueueResponse = {
  ready_to_post: TransactionResult[];
  needs_review: TransactionResult[];
  counts: Record<string, number>;
  total: number;
};
