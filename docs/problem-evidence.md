# Problem evidence

Source: anonymised fund-manager interview supplied for the Ylookup × Encode Rebuild Private Markets AI Hackathon (Product Track).

RedThread Ledger is scoped to one operational bottleneck in that interview: turning bank activity into journal entries that a fund manager can review without six or seven return trips.

## What the interview described

The fund manager relies on an administrator to prepare NAVs, financial statements and investor reporting. The review process was slow and repetitive.

Observed failure modes:

- Six or seven review turns for a single NAV
- Repeated errors in investor-specific fee calculations
- Numbers that did not reconcile across statements
- Limited quality control before work was returned
- A review burden that remained with the fund manager

The user was not primarily concerned about whether one turn took an hour or two days. The cost was the number of turns required before the output could be trusted.

## Why this is a product problem, not only a data-entry problem

The interview does not ask for autonomous posting. It asks for fewer, better-evidenced review cycles.

A useful system therefore has to:

1. Show where each proposed journal line came from
2. Separate confident mappings from unsupported ones
3. Refuse to invent a mapping when the source material does not support one
4. Keep the fund manager in the approval path

Document extraction alone does not solve this. The missing piece is an evidence-linked review queue.

## Problem we are solving in the MVP

**Bank statements → reviewable journal entries.**

Inputs from the official hackathon dataset:

- Seven anonymised bank statement PDFs
- Bank account mappings
- Legal entity, investor, vendor and related-party master lists
- Project code mappings
- Deal and position mappings
- Chart of accounts
- Allocation rules

Required behaviour:

- Extract the source transaction (reference, date, currency, amount, narrative, page)
- Resolve legal entity, account, counterparty, project, deal and position against supplied master data
- Classify the transaction
- Propose two balanced journal lines
- Mark the result `Ready to post` or `Needs review`
- Keep every decision inspectable against the source PDF and the reference row used

## Evidence of the workflow we are targeting

Example narrative from the dataset:

```text
PAYMENT FOR PURCHASE OF LOAN PRINCIPAL
PROJECT CEPHALUS
```

A correct system should be able to link that row to project Cephalus, instrument Funding Loan, and an Investment Transfer classification — or send it to review if the master data does not support the match.

Known unmatched rows in the dataset are preserved deliberately. Forcing every transaction into a confident answer would hide the same quality-control failure the interview described.

## What we are not claiming

- A successful match is not accounting approval
- The MVP does not produce a full NAV
- The MVP does not post into a production ledger
- Evaluation uses the supplied working workbook as ground truth, not as an application input

## Traceability for judges

| Interview signal | Product response |
|---|---|
| Too many review turns | Exception queue instead of a silent batch dump |
| Numbers that do not reconcile | Deterministic debit/credit and required-field checks |
| Limited QC before return | Evidence panel: source row, PDF page, candidate matches, rule or model decision |
| Trust, not speed of a single pass | `Needs review` when evidence is missing, ambiguous or inconsistent |
