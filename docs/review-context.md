# Review context fields

Review context is derived deterministically after all statement results have
been processed. It changes presentation and prioritization only; it never
changes classification, validation, status, or journal lines.

## Rules

- `issue_type` maps existing exception reasons to `counterparty`,
  `classification`, `project`, `amount`, or `other`.
- `issue_subtype` uses the first supported condition in this order: a journal
  line names a suspense account; source evidence is missing; the two leading
  candidates for the same field are within 0.03; confidence is below 0.65; a
  required field remains unresolved. Otherwise it is `null`.
- `attention_level` is `low` for Ready-to-post items. A Needs-review item is
  `high` when evidence is missing, suspense is used, a required value remains
  unresolved, confidence is below 0.60, or a same-field candidate gap is at
  most 0.03. It is `medium` when confidence is below 0.80, the candidate gap
  is below 0.10, or its absolute amount is at or above the review population's
  80th-percentile observation. Other Needs-review items are `low`.
- `cash_direction` uses the signed source amount first, then an explicit Cash
  Received/Disbursed journal type, and otherwise returns `unknown`.
- `suspense_flag` is true only when a proposed journal account or transaction
  type contains `suspense`.
- `match_reasons` describes chosen candidate records only. No reason is added
  when the matcher selected no candidate.
- `source_snapshot` copies existing statement evidence and transaction values.

The percentile rule is a queue-ordering aid, not a financial risk score.
