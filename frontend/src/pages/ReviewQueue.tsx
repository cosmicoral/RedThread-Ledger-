import { useEffect, useMemo, useRef, useState } from "react";
import { apiUrl } from "../api";
import type { AgentReviewResult, ExceptionReason, QueueResponse, TransactionResult } from "../types";
import { PdfEvidence } from "./PdfEvidence";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "needs_review", label: "Review" },
  { key: "ready_to_post", label: "Ready" },
] as const;

const REASON_LABEL: Record<ExceptionReason, string> = {
  missing_project: "Project match missing",
  missing_counterparty: "Counterparty uncertain",
  ambiguous_counterparty: "Counterparty uncertain",
  missing_position: "Position match missing",
  classification_review: "Classification uncertain",
  implausible_bank_charge: "Bank charge requires review",
  validation_failure: "Entry failed validation",
  missing_evidence: "Source evidence missing",
};

type EvidenceNode = "decision" | "classification" | "match" | "master" | "source";
type IssueCategory = "Counterparty" | "Classification" | "Project" | "Amount" | "Other";
type AttentionLevel = "high" | "medium" | "low";

function issueCategory(item: TransactionResult): IssueCategory {
  const apiCategory: Record<string, IssueCategory> = { counterparty: "Counterparty", classification: "Classification", project: "Project", amount: "Amount", other: "Other" };
  if (item.issue_type && apiCategory[item.issue_type]) return apiCategory[item.issue_type];
  const reasons = item.exception_reasons;
  if (reasons.includes("missing_counterparty") || reasons.includes("ambiguous_counterparty")) return "Counterparty";
  if (reasons.includes("classification_review")) return "Classification";
  if (reasons.includes("missing_project") || reasons.includes("missing_position")) return "Project";
  if (reasons.includes("implausible_bank_charge") || reasons.includes("validation_failure")) return "Amount";
  return "Other";
}

function candidateGap(item: TransactionResult): number | null {
  const sorted = item.candidates.map((candidate) => candidate.score).sort((a, b) => b - a);
  return sorted.length > 1 ? sorted[0] - sorted[1] : null;
}

function usesSuspense(item: TransactionResult): boolean {
  if (typeof item.suspense_flag === "boolean") return item.suspense_flag;
  return item.journal_lines.some((line) => `${line.account} ${line.transaction_type} ${line.memo}`.toLocaleLowerCase().includes("suspense"));
}

function largeAmountThreshold(items: TransactionResult[]): number {
  const values = items.map((item) => Math.abs(item.amount ?? 0)).filter(Boolean).sort((a, b) => a - b);
  return values[Math.max(0, Math.floor(values.length * 0.8))] ?? Number.POSITIVE_INFINITY;
}

function attentionLevel(item: TransactionResult, reviewItems: TransactionResult[]): AttentionLevel {
  if (item.attention_level) return item.attention_level;
  const gap = candidateGap(item);
  const missingEvidence = item.exception_reasons.includes("missing_evidence");
  const unresolved = !item.classification || (!item.counterparty && item.exception_reasons.some((reason) => reason.includes("counterparty")));
  if (usesSuspense(item) || missingEvidence || unresolved || item.confidence < 0.6 || (gap !== null && gap < 0.04)) return "high";
  const unusuallyLarge = Math.abs(item.amount ?? 0) >= largeAmountThreshold(reviewItems);
  return item.confidence < 0.8 || (gap !== null && gap < 0.1) || unusuallyLarge ? "medium" : "low";
}

function issueSubtype(item: TransactionResult, reviewItems: TransactionResult[]): string {
  if (item.issue_subtype) return item.issue_subtype.replaceAll("_", " ");
  const gap = candidateGap(item);
  if (usesSuspense(item)) return "Suspense account";
  if (item.exception_reasons.includes("missing_evidence")) return "Missing evidence";
  if (!item.classification) return "Unresolved classification";
  if (gap !== null && gap < 0.1) return "Close candidates";
  if (item.confidence < 0.65) return "Low confidence";
  if (Math.abs(item.amount ?? 0) >= largeAmountThreshold(reviewItems)) return "Large amount";
  if (item.exception_reasons.some((reason) => reason.startsWith("missing_"))) return "Missing match";
  return `${issueCategory(item)} review`;
}

function money(amount: number | null, currency: string | null): string {
  if (amount === null) return "—";
  const formatted = new Intl.NumberFormat("en-GB", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
  return currency ? `${formatted} ${currency}` : formatted;
}

function reasonFor(item: TransactionResult): string {
  return item.exception_reasons[0]
    ? REASON_LABEL[item.exception_reasons[0]]
    : item.status === "needs_review" ? "Requires review" : "Ready for review";
}

function isBalanced(item: TransactionResult): boolean {
  const debit = item.journal_lines.reduce((sum, line) => sum + line.debit, 0);
  const credit = item.journal_lines.reduce((sum, line) => sum + line.credit, 0);
  return item.journal_lines.length === 2 && Math.round((debit - credit) * 100) === 0;
}

export function ReviewQueue() {
  const [queue, setQueue] = useState<QueueResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const initialFilter = new URLSearchParams(window.location.search).get("filter") || "all";
  const [filter, setFilter] = useState(initialFilter);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [queueCollapsed, setQueueCollapsed] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState<IssueCategory | null>(null);
  const [attentionFilter, setAttentionFilter] = useState<AttentionLevel | null>(null);
  const [secondaryOpen, setSecondaryOpen] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({ high: true, medium: true, low: false, ready: false });
  const [visibleCounts, setVisibleCounts] = useState<Record<string, number>>({ high: 8, medium: 8, low: 8, ready: 8 });
  const [contextMode, setContextMode] = useState<"map" | "evidence">("map");
  const [activeNode, setActiveNode] = useState<EvidenceNode | null>(null);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [reverseStep, setReverseStep] = useState<number | null>(null);
  const reverseTimers = useRef<number[]>([]);
  const queueListRef = useRef<HTMLDivElement>(null);

  const load = () => {
    setError(null);
    fetch(apiUrl("/queue"))
      .then(async (response) => {
        if (!response.ok) throw new Error(`Queue failed (${response.status})`);
        return response.json();
      })
      .then((data: QueueResponse) => setQueue(data))
      .catch((cause: Error) => setError(cause.message));
  };

  useEffect(load, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (filter === "all") params.delete("filter");
    else params.set("filter", filter);
    const query = params.toString();
    window.history.replaceState(null, "", query ? `?${query}` : "/");
  }, [filter]);

  const mapItems = useMemo(() => {
    if (!queue) return [];
    const all = [...queue.needs_review, ...queue.ready_to_post];
    const filtered = filter === "all" ? all : all.filter((item) => item.status === filter);
    const query = search.trim().toLocaleLowerCase();
    return !query ? filtered : filtered.filter((item) => [
      item.transaction_id, item.counterparty, item.pulled_counterparty,
      item.legal_entity, item.evidence.narrative,
    ].some((value) => value?.toLocaleLowerCase().includes(query)));
  }, [queue, filter, search]);
  const reviewPool = useMemo(() => mapItems.filter((item) => item.status === "needs_review"), [mapItems]);
  const items = useMemo(() => {
    let result = categoryFilter ? mapItems.filter((item) => item.status === "needs_review" && issueCategory(item) === categoryFilter) : mapItems;
    if (attentionFilter) result = result.filter((item) => item.status === "needs_review" && attentionLevel(item, reviewPool) === attentionFilter);
    return result;
  }, [mapItems, categoryFilter, attentionFilter, reviewPool]);

  const selected = items.find((item) => item.transaction_id === selectedId) ?? items[0] ?? null;

  useEffect(() => () => reverseTimers.current.forEach(window.clearTimeout), []);

  const selectTransaction = (id: string) => {
    setSelectedId(id);
    setSourceOpen(false);
    window.setTimeout(() => queueListRef.current?.querySelector<HTMLElement>(`[data-transaction-id="${CSS.escape(id)}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" }), 0);
  };

  const groups = useMemo(() => {
    const needsReview = items.filter((item) => item.status === "needs_review");
    return [
      { key: "high", label: "High attention", items: needsReview.filter((item) => attentionLevel(item, reviewPool) === "high") },
      { key: "medium", label: "Medium attention", items: needsReview.filter((item) => attentionLevel(item, reviewPool) === "medium") },
      { key: "low", label: "Low attention", items: needsReview.filter((item) => attentionLevel(item, reviewPool) === "low") },
      { key: "ready", label: "Ready", items: items.filter((item) => item.status === "ready_to_post") },
    ].filter((group) => group.items.length > 0);
  }, [items, reviewPool]);

  const openEvidence = (node: EvidenceNode = "decision", showSource = false) => {
    setContextMode("evidence");
    setActiveNode(node);
    setSourceOpen(showSource);
  };

  const reverseTrace = () => {
    reverseTimers.current.forEach(window.clearTimeout);
    setContextMode("evidence");
    setSourceOpen(false);
    const path: EvidenceNode[] = ["decision", "classification", "match", "master", "source"];
    setReverseStep(0);
    setActiveNode(path[0]);
    reverseTimers.current = path.slice(1).map((node, index) => window.setTimeout(() => {
      setReverseStep(index + 1);
      setActiveNode(node);
      if (node === "source") setSourceOpen(true);
    }, (index + 1) * 300));
    reverseTimers.current.push(window.setTimeout(() => setReverseStep(null), 1550));
  };

  if (error) return (
    <main className="state-view">
      <h2>Review Queue</h2><p>{error}</p><button type="button" onClick={load}>Retry</button>
    </main>
  );
  if (!queue) return <main className="state-view"><p>Loading queue…</p></main>;

  return (
    <main className={`review-workspace${queueCollapsed ? " queue-collapsed" : ""}`}>
      {queueCollapsed ? (
        <aside className="queue-rail">
          <button type="button" onClick={() => setQueueCollapsed(false)} aria-label="Expand Review Queue">›<small>Review</small></button>
          <strong>{queue.counts.needs_review}</strong>
          <button type="button" onClick={() => setContextMode("map")}><span>●</span><small>Map</small></button>
          <button type="button" onClick={() => openEvidence("decision")}><span>│</span><small>Journal</small></button>
        </aside>
      ) : (
      <aside className="queue-pane">
        <div className="queue-controls">
        <header className="queue-header">
          <div><p className="wordmark">RedThread</p><h1>Review Queue</h1></div>
          <div className="queue-heading-actions"><strong>{queue.counts.needs_review} need attention</strong><button type="button" onClick={() => setQueueCollapsed(true)} aria-label="Collapse Review Queue">‹</button></div>
        </header>
        <input
          className="queue-search"
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search transactions"
          aria-label="Search transactions"
        />
        <nav className="queue-filters" aria-label="Queue filters">
          {FILTERS.map((item) => (
            <button key={item.key} className={filter === item.key ? "active" : ""} onClick={() => { setFilter(item.key); if (item.key === "ready_to_post") setExpandedGroups((current) => ({ ...current, ready: true })); if (item.key === "needs_review") setExpandedGroups((current) => ({ ...current, high: true, medium: true })); }} type="button">
              {item.label} <span>{item.key === "all" ? queue.total : queue.counts[item.key]}</span>
            </button>
          ))}
          <button className="filter-toggle" type="button" onClick={() => setSecondaryOpen((open) => !open)}>Filters {secondaryOpen ? "▴" : "▾"}</button>
        </nav>
        {secondaryOpen ? <div className="secondary-filters">
          {(["high", "medium", "low"] as AttentionLevel[]).map((level) => <button type="button" key={level} className={attentionFilter === level ? "active" : ""} onClick={() => setAttentionFilter(attentionFilter === level ? null : level)}>{level} attention</button>)}
          {(categoryFilter || attentionFilter) ? <button type="button" onClick={() => { setCategoryFilter(null); setAttentionFilter(null); }}>Clear</button> : null}
        </div> : null}
        </div>
        <div className="queue-list" ref={queueListRef}>
          {items.length === 0 ? <p className="muted">No matching transactions.</p> : groups.map((group) => (
            <section className={`queue-group group-${group.key}`} key={group.key}>
              <button className="group-heading" type="button" onClick={() => setExpandedGroups((current) => ({ ...current, [group.key]: !current[group.key] }))}>
                <span>{group.label}</span><strong>{group.items.length}</strong><i>{expandedGroups[group.key] ? "▾" : "▸"}</i>
              </button>
              {expandedGroups[group.key] ? <div>{group.items.slice(0, visibleCounts[group.key]).map((item) => (
            <button
              type="button"
              key={item.transaction_id}
              data-transaction-id={item.transaction_id}
              className={`transaction-row ${item.status} severity-${item.status === "ready_to_post" ? "ready" : attentionLevel(item, reviewPool)} category-${issueCategory(item).toLowerCase()}${selected?.transaction_id === item.transaction_id ? " selected" : ""}`}
              onClick={() => selectTransaction(item.transaction_id)}
            >
              <i className="thread-state" aria-hidden="true" />
              <span className="row-main">
                <strong>{item.counterparty || item.pulled_counterparty || "Counterparty unresolved"}</strong>
                <small>{item.legal_entity || item.evidence.account_name || "Entity unresolved"} · {item.date || "Date unavailable"}</small>
              </span>
              <span className="row-amount">{money(item.amount, item.currency)}</span>
              <span className="row-state">{item.status === "needs_review" ? issueCategory(item) : "Ready"}</span>
              <span className="row-arrow" aria-hidden="true">›</span>
            </button>
              ))}{group.items.length > visibleCounts[group.key] ? <button className="show-more" type="button" onClick={() => setVisibleCounts((current) => ({ ...current, [group.key]: current[group.key] + 12 }))}>Show 12 more ↓</button> : null}</div> : null}
            </section>
          ))}
        </div>
      </aside>
      )}
      {selected ? <TransactionDetail key={selected.transaction_id} item={selected} agentEnabled={Boolean(queue.agent_enabled)} onTrace={openEvidence} onReverse={reverseTrace} evidenceFocus={contextMode === "evidence" ? activeNode : null} /> : (
        <section className="empty-detail"><p>Select a transaction to review.</p></section>
      )}
      <ContextPanel
        mode={contextMode}
        setMode={setContextMode}
        item={selected}
        items={mapItems}
        selectedId={selected?.transaction_id ?? null}
        onSelect={selectTransaction}
        categoryFilter={categoryFilter}
        setCategoryFilter={setCategoryFilter}
        activeNode={activeNode}
        setActiveNode={setActiveNode}
        sourceOpen={sourceOpen}
        setSourceOpen={setSourceOpen}
        reverseStep={reverseStep}
      />
    </main>
  );
}

function TransactionDetail({ item, agentEnabled, onTrace, onReverse, evidenceFocus }: {
  item: TransactionResult;
  agentEnabled: boolean;
  onTrace: (node?: EvidenceNode, showSource?: boolean) => void;
  onReverse: () => void;
  evidenceFocus: EvidenceNode | null;
}) {
  const candidates = item.candidates.slice(0, 5);
  const [copied, setCopied] = useState(false);
  const reference = item.evidence.bank_reference || item.transaction_id;
  const copyReference = () => {
    void navigator.clipboard.writeText(reference).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    });
  };

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.matches("input, textarea, select, [contenteditable='true']")) return;
      if (event.key.toLowerCase() === "t") onTrace("decision");
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onTrace]);

  return (
    <section className={`detail-pane ${item.status}${evidenceFocus ? ` evidence-focused focus-${evidenceFocus}` : ""}`}>
      <header className="transaction-header">
        <div><h2>{item.counterparty || item.pulled_counterparty || "Counterparty unresolved"}</h2><p>{item.legal_entity || item.evidence.account_name || "Entity unresolved"} · {item.date || "Date unavailable"} · {item.cash_direction && item.cash_direction !== "unknown" ? `${item.cash_direction} · ` : ""}<button className="copy-reference" type="button" onClick={copyReference}>{reference}{copied ? " · Copied" : ""}</button></p></div>
        <div><strong>{money(item.amount, item.currency)}</strong><span>{item.status === "needs_review" ? "Needs review" : "Ready"}</span></div>
      </header>

      {item.status === "needs_review" ? (
        <section className="uncertainty">
          <p className="section-label">Issue</p><h3>{reasonFor(item)}</h3>
          {candidates.length > 0 ? <ul>{candidates.slice(0, 3).map((candidate) => (
            <li key={`${candidate.sheet}-${candidate.key}`}><span>{candidate.label}<i><b style={{ width: `${Math.round(candidate.score * 100)}%` }} /></i></span><strong>{Math.round(candidate.score * 100)}%</strong></li>
          ))}</ul> : <p className="muted">No supported candidate match is available.</p>}
          <AgentInvestigation item={item} agentEnabled={agentEnabled} />
        </section>
      ) : null}

      <section className="entry-section">
        <p className="section-label">Proposed entry</p>
        {usesSuspense(item) ? <p className="suspense-note">Suspense account used · review required</p> : null}
        {item.journal_lines.length ? (
          <table><tbody>{item.journal_lines.map((line, index) => (
            <tr key={`${line.account}-${index}`} tabIndex={0} onClick={onReverse} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") onReverse(); }}>
              <td><strong>{line.debit ? "Debit" : "Credit"}</strong><span>{line.account} · {line.transaction_type}</span></td>
              <td>{(line.debit || line.credit).toFixed(2)}</td>
              <td className="why-entry">Why this entry? →</td>
            </tr>
          ))}</tbody></table>
        ) : <p className="muted">No journal entry proposed.</p>}
        <p className={`balance ${isBalanced(item) ? "valid" : "invalid"}`}>{isBalanced(item) ? "Balanced ✓" : "Validation required"}</p>
      </section>

      <button className="trace-action" type="button" onClick={() => onTrace("decision")}>Trace evidence →</button>
      <p className="human-note">Human confirmation required before posting.</p>
    </section>
  );
}

function ContextPanel({ mode, setMode, item, items, selectedId, onSelect, categoryFilter, setCategoryFilter, activeNode, setActiveNode, sourceOpen, setSourceOpen, reverseStep }: {
  mode: "map" | "evidence";
  setMode: (mode: "map" | "evidence") => void;
  item: TransactionResult | null;
  items: TransactionResult[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  categoryFilter: IssueCategory | null;
  setCategoryFilter: (category: IssueCategory | null) => void;
  activeNode: EvidenceNode | null;
  setActiveNode: (node: EvidenceNode | null) => void;
  sourceOpen: boolean;
  setSourceOpen: (open: boolean) => void;
  reverseStep: number | null;
}) {
  const chosenLabels = item?.candidates.filter((candidate) => candidate.chosen).map((candidate) => candidate.label) ?? [];
  return (
    <aside className="context-pane" onClick={(event) => { if (event.target === event.currentTarget) setActiveNode(null); }}>
      <nav className="context-tabs">
        <button type="button" className={mode === "map" ? "active" : ""} onClick={() => setMode("map")}>Issue Map</button>
        <button type="button" className={mode === "evidence" ? "active" : ""} onClick={() => setMode("evidence")}>Evidence</button>
      </nav>
      {mode === "map" ? (
        <IssueLandscape items={items} selectedId={selectedId} onSelect={onSelect} categoryFilter={categoryFilter} setCategoryFilter={setCategoryFilter} />
      ) : item ? (
        <EvidenceDrawer item={item} activeNode={activeNode} setActiveNode={setActiveNode} sourceOpen={sourceOpen} setSourceOpen={setSourceOpen} reverseStep={reverseStep} chosenLabels={chosenLabels} />
      ) : <p className="muted">Select a transaction to trace its evidence.</p>}
    </aside>
  );
}

function IssueLandscape({ items, selectedId, onSelect, categoryFilter, setCategoryFilter }: {
  items: TransactionResult[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  categoryFilter: IssueCategory | null;
  setCategoryFilter: (category: IssueCategory | null) => void;
}) {
  const reviewItems = items.filter((item) => item.status === "needs_review");
  const categories: IssueCategory[] = ["Counterparty", "Classification", "Project", "Amount", "Other"];
  const populated = categories.filter((category) => reviewItems.some((item) => issueCategory(item) === category));
  const maxAmount = Math.max(...reviewItems.map((item) => Math.abs(item.amount ?? 0)), 1);
  const rank = { high: 3, medium: 2, low: 1 };
  const priority = [...reviewItems].sort((a, b) => rank[attentionLevel(b, reviewItems)] - rank[attentionLevel(a, reviewItems)] || Math.abs(b.amount ?? 0) - Math.abs(a.amount ?? 0)).slice(0, 3);
  return <section className="issue-map">
    <header><p className="section-label">Operational view</p><h3>Issue Landscape</h3><span>{reviewItems.length} needs review</span></header>
    {reviewItems.length === 0 ? <div className="queue-clear"><i /><h3>Queue clear.</h3><p>No transactions currently need review.</p></div> : <>
      <div className="landscape-categories">
        {populated.map((category) => <button type="button" key={category} className={categoryFilter === category ? "active" : ""} onClick={() => setCategoryFilter(categoryFilter === category ? null : category)}><i className={`category-${category.toLowerCase()}`} />{category}<strong>{reviewItems.filter((item) => issueCategory(item) === category).length}</strong></button>)}
        {populated.length < categories.length ? <span>Other categories 0</span> : null}
      </div>
      <div className="issue-landscape">
        {(["high", "medium", "low"] as AttentionLevel[]).map((level) => {
          const laneItems = reviewItems.filter((item) => attentionLevel(item, reviewItems) === level && (!categoryFilter || issueCategory(item) === categoryFilter));
          const subtypes = [...new Set(laneItems.map((item) => issueSubtype(item, reviewItems)))];
          return <section className={`attention-lane attention-${level}`} key={level}>
            <header><span>{level} attention</span><strong>{laneItems.length}</strong></header>
            {subtypes.length === 0 ? <p>None</p> : subtypes.map((subtype) => <div className="subtype-row" key={subtype}>
              <small>{subtype}</small><div className="landscape-dots">{laneItems.filter((item) => issueSubtype(item, reviewItems) === subtype).map((transaction) => {
                const size = 7 + Math.sqrt(Math.abs(transaction.amount ?? 0) / maxAmount) * 10;
                const gap = candidateGap(transaction);
                return <button type="button" key={transaction.transaction_id} className={`issue-dot category-${issueCategory(transaction).toLowerCase()} severity-${level}${selectedId === transaction.transaction_id ? " selected" : ""}`} style={{ width: size, height: size }} onClick={() => { setCategoryFilter(null); onSelect(transaction.transaction_id); }} aria-label={`${transaction.counterparty || "Unresolved"}, ${issueSubtype(transaction, reviewItems)}`}>
                  <span>{transaction.counterparty || transaction.pulled_counterparty || "Unresolved"}<b>{money(transaction.amount, transaction.currency)}</b><small>{issueSubtype(transaction, reviewItems)} · confidence {Math.round(transaction.confidence * 100)}%{gap !== null ? ` · candidate gap ${Math.round(gap * 100)}pt` : ""}<br />{transaction.evidence.bank_reference || transaction.transaction_id}</small></span>
                </button>;
              })}</div>
            </div>)}
          </section>;
        })}
      </div>
      <div className="review-next"><p className="section-label">Review next</p><ol>{priority.map((transaction) => <li key={transaction.transaction_id}><button type="button" onClick={() => onSelect(transaction.transaction_id)}><span>{transaction.legal_entity || transaction.counterparty || "Unresolved entity"}<small>{issueCategory(transaction)} · {issueSubtype(transaction, reviewItems)}</small></span><strong>{money(transaction.amount, transaction.currency)}</strong></button></li>)}</ol></div>
    </>}
  </section>;
}

function EvidenceDrawer({ item, activeNode, setActiveNode, sourceOpen, setSourceOpen, reverseStep, chosenLabels }: {
  item: TransactionResult;
  activeNode: EvidenceNode | null;
  setActiveNode: (node: EvidenceNode | null) => void;
  sourceOpen: boolean;
  setSourceOpen: (open: boolean) => void;
  reverseStep: number | null;
  chosenLabels: string[];
}) {
  const snapshot = item.source_snapshot;
  const nodes: Array<{ key: EvidenceNode; title: string; value: string }> = [
    { key: "decision", title: "Accounting decision", value: item.journal_lines.map((line) => line.transaction_type).join(" / ") || "No entry proposed" },
    { key: "classification", title: "Classification", value: item.classification || "Unresolved" },
    { key: "match", title: "Counterparty / project match", value: [item.counterparty, item.project_code, item.position].filter(Boolean).join(" · ") || "Unresolved" },
    { key: "master", title: "Master-data evidence", value: chosenLabels.join(" · ") || `${item.candidates.length} candidate matches` },
    { key: "source", title: "Original bank transaction", value: snapshot?.raw_description || item.evidence.narrative || "Narrative unavailable" },
  ];
  return (
    <aside className={`evidence-drawer${reverseStep !== null ? " reversing" : ""}`} aria-label="Evidence trace">
      <header><div><p className="section-label">Evidence trace</p><h3>{snapshot?.reference || item.evidence.bank_reference || item.transaction_id}</h3></div><span>{snapshot?.document_name || item.evidence.document_name} · p.{snapshot?.page ?? item.evidence.page ?? "?"}</span></header>
      {reverseStep !== null ? <p className="reverse-status">Tracing entry back to source…</p> : null}
      <div className="evidence-thread">
        {nodes.map((node) => (
          <button
            type="button"
            key={node.key}
            className={`${activeNode === node.key ? "active" : ""}${node.value === "Unresolved" ? " unresolved" : ""}`}
            onMouseEnter={() => setActiveNode(node.key)}
            onClick={() => { setActiveNode(node.key); if (node.key === "source") setSourceOpen(true); }}
          >
            <i aria-hidden="true" /><span><strong>{node.title}</strong><small>{node.value}</small></span>
          </button>
        ))}
      </div>
      <div className="evidence-focus">
        {activeNode === "classification" ? <><strong>Classification</strong><p>{item.classification || "No supported classification"} · confidence {Math.round(item.confidence * 100)}%</p></> : null}
        {activeNode === "match" || activeNode === "master" ? <><strong>Matching evidence</strong>{item.match_reasons?.length ? <ul>{item.match_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul> : <ul>{item.candidates.slice(0, 5).map((candidate) => <li key={`${candidate.sheet}-${candidate.key}`}>{candidate.chosen ? "Chosen: " : "Candidate: "}{candidate.label} · {Math.round(candidate.score * 100)}%</li>)}</ul>}</> : null}
        {activeNode === "decision" ? <><strong>Proposed accounting decision</strong><p>{item.journal_lines.length} journal line{item.journal_lines.length === 1 ? "" : "s"} · {isBalanced(item) ? "balanced" : "requires validation"}</p></> : null}
        {activeNode === "source" ? <><strong>Source transaction</strong><p>{snapshot?.raw_description || item.evidence.narrative || "Narrative unavailable"}</p>{snapshot?.account_number ? <p>Account {snapshot.account_number} · {snapshot.amount ?? "—"} {snapshot.currency || ""}</p> : null}</> : null}
      </div>
      {sourceOpen ? <PdfEvidence documentName={item.evidence.document_name} page={item.evidence.page} spotlighted={activeNode === "source"} /> : (
        <button className="source-action" type="button" onClick={() => { setActiveNode("source"); setSourceOpen(true); }}>View source document →</button>
      )}
    </aside>
  );
}

function AgentInvestigation({ item, agentEnabled }: { item: TransactionResult; agentEnabled: boolean }) {
  const [review, setReview] = useState<AgentReviewResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const investigate = () => {
    setBusy(true); setError(null);
    fetch(apiUrl(`/transactions/${encodeURIComponent(item.transaction_id)}/agent-review`), { method: "POST" })
      .then(async (response) => {
        const data = await response.json().catch(() => null) as AgentReviewResult | { detail?: string | { message?: string } } | null;
        if (!response.ok) {
          const detail = data && "detail" in data ? data.detail : null;
          const message = typeof detail === "string" ? detail : detail?.message;
          throw new Error(message || `Investigation failed (${response.status})`);
        }
        return data as AgentReviewResult;
      })
      .then((data) => setReview(data))
      .catch((cause: Error) => setError(cause.message))
      .finally(() => setBusy(false));
  };
  if (!review) return (
    <div className="agent-compact">
      <button type="button" onClick={investigate} disabled={busy}>{busy ? "Investigating evidence…" : "Investigate with AI"}</button>
      {busy ? <div className="agent-progress" aria-live="polite"><i /><span>Checking references and available matches</span><small>Presentation of the investigation while the request completes.</small></div> : null}
      {!agentEnabled ? <small>AI is not configured for this environment.</small> : null}
      {error ? <small className="agent-error">{error}</small> : null}
    </div>
  );
  const evidence = review.tool_trace.filter((entry) => entry.ok).slice(0, 3);
  return (
    <div className="agent-result">
      <p className="section-label">AI finding</p>
      <h3>{review.status === "agent_suggested" ? "Suggested resolution" : "Human review still required"}</h3>
      <p>{review.summary}</p><p><strong>Confidence</strong> {Math.round(review.confidence * 100)}%</p>
      {evidence.length ? <ul>{evidence.map((entry, index) => <li key={`${entry.step}-${index}`}>{entry.result_summary}</li>)}</ul> : null}
      {review.unresolved_questions[0] ? <p><strong>Unresolved</strong> {review.unresolved_questions[0]}</p> : null}
      {review.proposed_journal_lines.length ? <p><strong>Proposed entry</strong> {review.proposed_journal_lines.length} journal lines</p> : null}
      <p><strong>Validation</strong> {review.deterministic_validation.valid ? "Passed" : "Requires review"}</p>
      <small>AI suggestion · Human confirmation required</small>
    </div>
  );
}
