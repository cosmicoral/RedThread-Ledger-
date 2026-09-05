import { useEffect, useMemo, useState } from "react";
import type { QueueResponse, TransactionResult } from "../types";
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
  { key: "validation_failure", label: "Validation failure" },
];

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

export function ReviewQueue() {
  const [queue, setQueue] = useState<QueueResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    fetch("/queue")
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Queue failed (${response.status})`);
        }
        return response.json();
      })
      .then((data: QueueResponse) => setQueue(data))
      .catch((err: Error) => setError(err.message));
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
    return all.filter((item) => item.exception_reasons.includes(filter as TransactionResult["exception_reasons"][number]));
  }, [queue, filter]);

  const selected =
    items.find((item) => item.transaction_id === selectedId) ?? items[0] ?? null;

  if (error) {
    return <p className="empty">Could not load the review queue. Is the API running?</p>;
  }
  if (!queue) {
    return <p className="empty">Loading review queue…</p>;
  }

  return (
    <main className="workspace">
      <section className="panel">
        <div className="panel-header">
          <h2>Review queue</h2>
          <p>
            {queue.total} extracted transactions · {queue.counts.ready_to_post} ready ·{" "}
            {queue.counts.needs_review} need review
          </p>
        </div>
        <ul className="filters">
          {FILTERS.map((item) => (
            <li key={item.key}>
              <button
                className={filter === item.key ? "active" : ""}
                onClick={() => setFilter(item.key)}
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
        {items.length === 0 ? (
          <p className="empty">
            No transactions in this bucket. Run <code>make sync-data</code> then
            restart the API if the queue is empty.
          </p>
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
                  </span>
                  <strong>{money(item.amount, item.currency)}</strong>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {selected ? <Detail item={selected} /> : null}
    </main>
  );
}

function Detail({ item }: { item: TransactionResult }) {
  const chosen = item.candidates.filter((candidate) => candidate.chosen);
  const others = item.candidates.filter((candidate) => !candidate.chosen).slice(0, 6);

  return (
    <section className="panel detail">
      <div className="panel-header">
        <h2>{item.status === "ready_to_post" ? "Ready to post" : "Needs review"}</h2>
        <p>
          {item.classification || "No classification"} · {item.legal_entity || "No legal entity"}
        </p>
      </div>

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
        <div>
          <dt>Exceptions</dt>
          <dd>{item.exception_reasons.join(", ") || "None"}</dd>
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
          <li key={`${candidate.sheet}-${candidate.key}`}>
            Candidate {candidate.field}: {candidate.label} · {candidate.sheet} ·{" "}
            {candidate.score.toFixed(2)}
          </li>
        ))}
      </ul>

      <h3>Proposed journal</h3>
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
        </tbody>
      </table>

      <h3>Source evidence</h3>
      <PdfEvidence documentName={item.evidence.document_name} page={item.evidence.page} />
    </section>
  );
}
