import { useEffect, useMemo, useState } from "react";
import { apiUrl } from "../api";
import type {
  AgentReviewResult,
  AgentStep,
  ExceptionReason,
  QueueResponse,
  TransactionResult,
} from "../types";
import { PdfEvidence } from "./PdfEvidence";

const FILTERS: { key: string; label: string }[] = [
  { key: "all", label: "All" },
  { key: "ready_to_post", label: "Ready to post" },
  { key: "needs_review", label: "Needs review" },
  { key: "missing_project", label: "Missing project" },
  { key: "missing_counterparty", label: "Missing counterparty" },
  { key: "ambiguous_counterparty", label: "Ambiguous counterparty" },
  { key: "missing_position", label: "Missing position" },
  { key: "classification_review", label: "Classification review" },
  { key: "implausible_bank_charge", label: "Implausible bank charge" },
  { key: "validation_failure", label: "Validation failure" },
];

const REASON_LABEL: Record<ExceptionReason, string> = {
  missing_project: "Project code could not be uniquely matched",
  missing_counterparty: "No unique counterparty in the master lists",
  ambiguous_counterparty: "More than one plausible counterparty",
  missing_position: "Deal or position could not be resolved",
  classification_review: "Classification needs a human decision",
  implausible_bank_charge: "Bank-charge posting is implausible or weakly supported",
  validation_failure: "Journal lines failed a deterministic check",
  missing_evidence: "Source document or page is missing",
};

function money(amount: number | null, currency: string | null): string {
  if (amount === null) {
    return "—";
  }
  const value = new Intl.NumberFormat("en-GB", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
  return currency ? `${value} ${currency}` : value;
}

function citation(item: TransactionResult): string {
  const page = item.evidence.page ?? "?";
  return `${item.evidence.document_name || "unknown document"} · p.${page}`;
}

function reviewReasons(item: TransactionResult): string[] {
  if (item.exception_reasons.length === 0) {
    return item.status === "needs_review" ? ["Held for human review"] : [];
  }
  return item.exception_reasons.map((reason) => REASON_LABEL[reason] || reason);
}

function journalBalanced(item: TransactionResult): boolean {
  const debit = item.journal_lines.reduce((sum, line) => sum + line.debit, 0);
  const credit = item.journal_lines.reduce((sum, line) => sum + line.credit, 0);
  return item.journal_lines.length === 2 && Math.round((debit - credit) * 100) === 0;
}

export function ReviewQueue() {
  const [queue, setQueue] = useState<QueueResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const initialFilter = new URLSearchParams(window.location.search).get("filter") || "all";
  const [filter, setFilter] = useState(initialFilter);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const load = () => {
    setError(null);
    setQueue(null);
    fetch(apiUrl("/queue"))
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Queue failed (${response.status})`);
        }
        return response.json();
      })
      .then((data: QueueResponse) => setQueue(data))
      .catch((err: Error) => setError(err.message));
  };

  useEffect(() => {
    load();
  }, []);

  const items = useMemo(() => {
    if (!queue) {
      return [];
    }
    const all = [...queue.ready_to_post, ...queue.needs_review];
    if (filter === "all") {
      return all;
    }
    if (filter === "ready_to_post" || filter === "needs_review") {
      return all.filter((item) => item.status === filter);
    }
    return all.filter((item) =>
      item.exception_reasons.includes(filter as ExceptionReason),
    );
  }, [queue, filter]);

  const selected =
    items.find((item) => item.transaction_id === selectedId) ?? items[0] ?? null;

  if (error) {
    return (
      <main className="panel state-panel">
        <h2>Could not load the review queue</h2>
        <p>{error}. Confirm the API is running on port 8000, then retry.</p>
        <button type="button" onClick={load}>
          Retry
        </button>
      </main>
    );
  }
  if (!queue) {
    return (
      <main className="panel state-panel">
        <h2>Loading review queue</h2>
        <p>Extracting statements and matching allowlisted reference data…</p>
      </main>
    );
  }

  return (
    <main className="workspace">
      <section className="panel">
        <div className="summary-strip" aria-label="Queue summary">
          <div>
            <strong>{queue.total}</strong>
            <span>extracted</span>
          </div>
          <div>
            <strong>{queue.counts.ready_to_post}</strong>
            <span>ready to post</span>
          </div>
          <div>
            <strong>{queue.counts.needs_review}</strong>
            <span>needs review</span>
          </div>
        </div>
        <p className="approval-banner">
          Human approval required. RedThread proposes journal lines; it does not
          post, approve, or replace a fund accountant.
        </p>
        <div className="panel-header">
          <h2>Review queue</h2>
          <p>
            {queue.total} / {queue.counts.ready_to_post} / {queue.counts.needs_review}
            {" "}· extracted / ready / review
          </p>
        </div>
        <ul className="filters">
          {FILTERS.map((item) => (
            <li key={item.key}>
              <button
                className={filter === item.key ? "active" : ""}
                onClick={() => {
                  setFilter(item.key);
                  const params = new URLSearchParams(window.location.search);
                  if (item.key === "all") {
                    params.delete("filter");
                  } else {
                    params.set("filter", item.key);
                  }
                  const query = params.toString();
                  window.history.replaceState(null, "", query ? `?${query}` : "/");
                }}
                type="button"
              >
                {item.label}
                <strong>
                  {item.key === "all"
                    ? queue.total
                    : queue.counts[item.key] ?? 0}
                </strong>
              </button>
            </li>
          ))}
        </ul>
        {queue.total === 0 ? (
          <p className="empty">
            No statements loaded. The seven hackathon PDFs should live in{" "}
            <code>data/hackathon/bank-statements/</code>.
          </p>
        ) : items.length === 0 ? (
          <p className="empty">No transactions in this filter.</p>
        ) : (
          <ul className="queue">
            {items.map((item) => (
              <li key={item.transaction_id}>
                <button
                  className={item.transaction_id === selected?.transaction_id ? "row active" : "row"}
                  onClick={() => setSelectedId(item.transaction_id)}
                  type="button"
                >
                  <span>
                    <em>{item.evidence.bank_reference || "No ref"}</em>
                    {item.classification || "Unclassified"}
                    <small>{citation(item)}</small>
                  </span>
                  <strong>{money(item.amount, item.currency)}</strong>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {selected ? (
        <Detail item={selected} agentEnabled={Boolean(queue.agent_enabled)} />
      ) : queue.total > 0 ? (
        <section className="panel state-panel">
          <h2>Select a transaction</h2>
          <p>Open a Ready to post or Needs review row to inspect evidence.</p>
        </section>
      ) : null}
    </main>
  );
}

const AGENT_STEPS: { key: AgentStep; label: string }[] = [
  { key: "evidence", label: "Evidence" },
  { key: "internal_lookup", label: "Internal lookup" },
  { key: "external_research", label: "External research" },
  { key: "validation", label: "Validation" },
  { key: "recommendation", label: "Recommendation" },
];

function AgentPanel({
  item,
  agentEnabled,
}: {
  item: TransactionResult;
  agentEnabled: boolean;
}) {
  const [review, setReview] = useState<AgentReviewResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setReview(null);
    setError(null);
    setBusy(false);
  }, [item.transaction_id]);

  const runReview = () => {
    setBusy(true);
    setError(null);
    fetch(apiUrl(`/transactions/${encodeURIComponent(item.transaction_id)}/agent-review`), {
      method: "POST",
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Agent review failed (${response.status})`);
        }
        return response.json();
      })
      .then((data: AgentReviewResult) => setReview(data))
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false));
  };

  const done = new Set((review?.tool_trace || []).map((entry) => entry.step));
  if (review) {
    done.add("validation");
    done.add("recommendation");
  }

  return (
    <div className="agent-panel">
      <h3>Agent review</h3>
      <p>
        Optional Gemini exception pass. It can propose a resolution but cannot
        post, approve, or change the deterministic result.
        {agentEnabled ? "" : " The agent flag is off; the request will fall back safely."}
      </p>
      {item.status === "needs_review" ? (
        <button type="button" onClick={runReview} disabled={busy}>
          {busy ? "Running agent review…" : "Run agent review"}
        </button>
      ) : (
        <p className="empty">Agent review is only offered on Needs-review rows.</p>
      )}
      {error ? <p className="review-reason">{error}</p> : null}
      {review ? (
        <>
          <ol className="agent-trace" aria-label="Agent step trace">
            {AGENT_STEPS.map((step) => (
              <li key={step.key} className={done.has(step.key) ? "done" : "pending"}>
                {step.label}
              </li>
            ))}
          </ol>
          <p>
            <strong>
              {review.status === "agent_suggested" ? "Agent suggested" : "Needs human review"}
            </strong>
            {" · "}
            confidence {(review.confidence * 100).toFixed(0)}%
          </p>
          <p>{review.summary}</p>
          {review.fallback ? (
            <p className="review-reason">
              Fallback: {review.fallback_reason || "Gemini unavailable"}. Original
              deterministic result is unchanged.
            </p>
          ) : null}
          <p className="approval-banner">
            Human approval required. The original Ready/Needs-review decision was
            not modified.
          </p>
          {review.unresolved_questions.length > 0 ? (
            <ul>
              {review.unresolved_questions.map((question) => (
                <li key={question}>{question}</li>
              ))}
            </ul>
          ) : null}
          {review.proposed_journal_lines.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Proposed account</th>
                  <th>Type</th>
                  <th>Debit</th>
                  <th>Credit</th>
                </tr>
              </thead>
              <tbody>
                {review.proposed_journal_lines.map((line, index) => (
                  <tr key={`${line.account}-${index}`}>
                    <td>{line.account}</td>
                    <td>{line.transaction_type}</td>
                    <td>{line.debit.toFixed(2)}</td>
                    <td>{line.credit.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {review.external_citations.length > 0 ? (
            <ul>
              {review.external_citations.map((citation) => (
                <li key={citation.uri || citation.title}>
                  {citation.uri ? (
                    <a href={citation.uri} target="_blank" rel="noreferrer">
                      {citation.title || citation.uri}
                    </a>
                  ) : (
                    citation.title
                  )}
                </li>
              ))}
            </ul>
          ) : null}
          <p>
            Deterministic validation:{" "}
            {review.deterministic_validation.valid ? "passed" : "not passed"}
          </p>
        </>
      ) : null}
    </div>
  );
}

function Detail({
  item,
  agentEnabled,
}: {
  item: TransactionResult;
  agentEnabled: boolean;
}) {
  const chosen = item.candidates.filter((candidate) => candidate.chosen);
  const others = item.candidates.filter((candidate) => !candidate.chosen).slice(0, 6);
  const debit = item.journal_lines.reduce((sum, line) => sum + line.debit, 0);
  const credit = item.journal_lines.reduce((sum, line) => sum + line.credit, 0);
  const reasons = reviewReasons(item);

  return (
    <section className="panel detail">
      <p className="approval-banner">
        Human approval required before this proposal can be posted.
      </p>
      <div className="panel-header">
        <h2>{item.status === "ready_to_post" ? "Ready to post" : "Needs review"}</h2>
        <p>
          {item.classification || "No classification"} · confidence{" "}
          {(item.confidence * 100).toFixed(0)}%
        </p>
      </div>
      <p className="citation">Source citation: {citation(item)}</p>
      {reasons.length > 0 ? (
        <p className="review-reason">Review reason: {reasons.join("; ")}</p>
      ) : (
        <p className="review-reason">Review reason: none — still requires human approval.</p>
      )}

      <dl className="facts">
        <div>
          <dt>Narrative</dt>
          <dd>{item.evidence.narrative || "—"}</dd>
        </div>
        <div>
          <dt>Counterparty</dt>
          <dd>
            {item.counterparty || "Unresolved"}
            {item.pulled_counterparty ? ` (pulled: ${item.pulled_counterparty})` : ""}
          </dd>
        </div>
        <div>
          <dt>Project / position</dt>
          <dd>
            {item.project_code || "No project"} · {item.position || "No position"}
          </dd>
        </div>
      </dl>

      <h3>Master-data match</h3>
      <ul className="matches">
        {chosen.length === 0 && others.length === 0 ? (
          <li>No reference-data hit. Left unresolved on purpose.</li>
        ) : null}
        {chosen.map((candidate) => (
          <li key={`${candidate.sheet}-${candidate.key}`}>
            <strong>Chosen</strong> {candidate.field}: {candidate.label} · {candidate.sheet} ·{" "}
            {candidate.score.toFixed(2)}
          </li>
        ))}
        {others.map((candidate) => (
          <li key={`${candidate.sheet}-${candidate.key}-alt`}>
            Candidate {candidate.field}: {candidate.label} · {candidate.sheet} ·{" "}
            {candidate.score.toFixed(2)}
          </li>
        ))}
      </ul>

      <h3>Proposed journal {journalBalanced(item) ? "(balanced)" : "(not balanced)"}</h3>
      {item.journal_lines.length === 0 ? (
        <p className="empty">No journal lines proposed.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Account</th>
              <th>Type</th>
              <th>Debit</th>
              <th>Credit</th>
            </tr>
          </thead>
          <tbody>
            {item.journal_lines.map((line, index) => (
              <tr key={`${line.account}-${index}`}>
                <td>{line.account}</td>
                <td>{line.transaction_type}</td>
                <td>{line.debit.toFixed(2)}</td>
                <td>{line.credit.toFixed(2)}</td>
              </tr>
            ))}
            <tr>
              <td colSpan={2}>Totals</td>
              <td>{debit.toFixed(2)}</td>
              <td>{credit.toFixed(2)}</td>
            </tr>
          </tbody>
        </table>
      )}

      <h3>Source evidence</h3>
      <PdfEvidence documentName={item.evidence.document_name} page={item.evidence.page} />
      <AgentPanel item={item} agentEnabled={agentEnabled} />
    </section>
  );
}
