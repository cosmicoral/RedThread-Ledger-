# RedThread Ledger

**Evidence-linked bank statement processing for private-market fund operations.**

RedThread Ledger turns bank statements and fund reference data into reviewable journal entries. Every proposed accounting decision links back to the source transaction and the reference data used to make it.

Built for the **Ylookup × Encode Rebuild Private Markets AI Hackathon — Product Track**.

> **Status:** Hackathon MVP under active development.  
> The implementation was started from a new repository during the hackathon.

## The problem

Fund managers rely on administrators to prepare NAVs, financial statements and investor reporting, but the review process is often slow and repetitive.

In the anonymised Ylookup interview provided for the hackathon, a fund manager described:

- Six or seven review turns for a single NAV
- Repeated errors in investor-specific fee calculations
- Numbers that did not reconcile across statements
- Limited quality control before work was returned
- A review burden that remained with the fund manager

The user was not primarily concerned about whether one turn took an hour or two days. The real cost was the number of turns required before the output could be trusted.

RedThread Ledger addresses one part of that problem: converting bank activity into journal entries with a visible evidence trail and an explicit review queue.

## The product

RedThread Ledger processes a fund’s bank statements through six stages:

1. Extract statement transactions
2. Identify the legal entity and bank account
3. Resolve the sender or beneficiary
4. Match project codes, deals and positions
5. Classify the transaction
6. Generate and validate double-entry journal lines

The product separates transactions into two outcomes:

- **Ready to post** — required fields are resolved and validation checks pass
- **Needs review** — evidence is missing, ambiguous or inconsistent

RedThread does not invent a mapping when the source material does not support one.

## Hackathon MVP

The MVP focuses on the official **Bank Statements to Journal Entries** dataset.

### Inputs

- Seven anonymised bank statement PDFs
- Bank account mappings
- Legal entity, investor, vendor and related-party master lists
- Project code mappings
- Deal and position mappings
- Chart of accounts
- Allocation rules

### Outputs

For each transaction:

- Bank reference
- Source document and page
- Transaction date, currency and amount
- Extracted narrative
- Matched legal entity
- Matched counterparty
- Project code
- Classification
- Transaction type
- Deal and position, where applicable
- Confidence and review status
- Two proposed journal lines

The final output can be exported in the structure required by the supplied `DIU` workbook.

## User workflow

### 1. Upload

The user uploads one or more bank statements and selects the relevant fund reference data.

### 2. Review exceptions

RedThread shows a transaction-level queue:

- Ready to post
- Missing project
- Ambiguous counterparty
- Missing position
- Classification review
- Validation failure

### 3. Inspect evidence

Selecting a transaction shows:

- The original statement row
- The relevant narrative
- The PDF page
- Candidate master-data matches
- The rule or model decision
- The proposed journal lines

### 4. Approve and export

The user can:

- Approve the proposal
- Change a mapping
- Mark the transaction for follow-up
- Export validated journal entries

## Example

A bank narrative contains:

```text
PAYMENT FOR PURCHASE OF LOAN PRINCIPAL
PROJECT CEPHALUS
```

RedThread links the transaction to:

```text
Project:        Cephalus
Instrument:     Funding Loan
Classification: Investment Transfer
Status:         Ready to post
```

The evidence panel retains the original narrative, bank reference and PDF page alongside the matched deal and position.

If the project or counterparty cannot be resolved from the supplied master data, the result is marked `Needs review` rather than silently guessed.

## Why this is different

Document AI tools often stop after extracting text.

RedThread follows the full operational thread:

```text
source transaction
        ↓
extracted evidence
        ↓
master-data match
        ↓
accounting classification
        ↓
journal lines
        ↓
validation and human approval
```

The goal is not autonomous accounting. The goal is to reduce manual review while keeping every decision auditable.

## Architecture

```text
Bank statement PDFs
        │
        ▼
Transaction extraction
        │
        ▼
Entity and account resolution
        │
        ▼
Counterparty and project matching
        │
        ▼
Classification and position resolution
        │
        ▼
Double-entry rule engine
        │
        ▼
Validation and exception detection
        │
        ▼
Review UI and journal export
```

The implementation separates probabilistic and deterministic work:

- AI assists with narrative interpretation and semantic matching
- Retrieval limits matches to known reference data
- Accounting rules generate the journal structure
- Deterministic checks validate required fields and debit/credit balance
- Low-confidence or unsupported decisions go to human review

## Evaluation

The supplied working workbook is used as ground truth for evaluation, not as an application input.

We measure:

| Area | Metric |
|---|---|
| Statement extraction | Exact match for reference, date, currency and amount |
| Counterparty resolution | Match accuracy against reviewed mappings |
| Project resolution | Match accuracy and unsupported-match rate |
| Classification | Accuracy by transaction category |
| Position resolution | Exact match against reviewed positions |
| Journal generation | Field-level and full-entry exact match |
| Accounting validity | Two lines per batch and balanced debit/credit |
| Exception handling | Precision and recall for `Needs review` |
| Evidence | Valid source document and page reference |

Known unmatched rows in the dataset are preserved deliberately. A correct system should identify uncertainty rather than force every transaction into a confident answer.

To reduce leakage, evaluation splits are made at statement level. The ground-truth `Staging Sheet` and `DIU` sheets are never loaded by the production pipeline.

## Quick start

The submission is designed to run with one command:

```bash
make demo
```

Then open:

```text
http://localhost:3000
```

The repository includes anonymised demo fixtures. If no model API key is configured, the application starts in demo mode so the interface and evidence workflow can still be reviewed.

For model-backed processing, copy the example environment file and add a key locally:

```bash
cp .env.example .env
```

Never commit API keys.

## Development commands

```bash
make demo       # Start the application
make test       # Run unit and integration tests
make eval       # Evaluate against the held-out statements
make lint       # Run code-quality checks
```

## Repository structure

```text
redthread-ledger/
├── frontend/                 # Review interface
├── backend/
│   ├── extraction/           # PDF and transaction extraction
│   ├── matching/             # Entity, counterparty and project matching
│   ├── classification/       # Transaction classification
│   ├── journal/              # Double-entry generation
│   ├── validation/           # Accounting and evidence checks
│   └── api/                  # Application API
├── tests/
│   ├── fixtures/
│   ├── unit/
│   └── integration/
├── evaluation/               # Dataset evaluation harness
├── data/
│   └── demo/                 # Approved anonymised demo fixtures
├── docs/
│   ├── problem-evidence.md
│   ├── architecture.md
│   └── evaluation.md
├── .env.example
├── docker-compose.yml
├── Makefile
└── README.md
```

## Scope

### Included in the hackathon MVP

- Digital bank statement PDFs
- Reference-data-assisted matching
- Transaction classification
- Deal and position resolution
- Double-entry generation
- Evidence citations
- Human review queue
- Excel export
- Reproducible evaluation

### Stretch goal

Apply the same evidence and exception architecture to the supplied investor-level GL migration workflow:

- Map legal entities and accounts between systems
- Resolve deals, positions and investors
- Apply batch-type override rules
- Reconcile movements before upload
- Generate the target-system loader

### Out of scope for the hackathon

- Scanned-document OCR
- Autonomous posting into a production accounting system
- Legal or accounting approval
- Technology and ESG due diligence
- Full NAV production

## Data handling

The project uses anonymised hackathon data.

Unless the organisers explicitly approve public redistribution, the complete source dataset should remain outside the repository and under a gitignored `data/raw/` directory. Only approved demo fixtures should be committed.

The application does not require or store reversal keys, production credentials or real client data.

## Limitations

RedThread Ledger is a decision-support prototype.

- A successful match does not constitute accounting approval
- Low-confidence and unsupported mappings require human review
- Results depend on the completeness of the supplied master data
- Material journal entries should be reviewed by a qualified fund accountant
- The current MVP is evaluated only on the supplied anonymised workflows

## Hackathon submission

- **Track:** Product Track
- **Problem source:** Anonymised fund-manager NAV workflow interview
- **Dataset:** Bank Statements to Journal Entries
- **Demo video:** Add link before submission
- **Live application:** Add link if deployed
- **Run locally:** `make demo`

## Team

Add team members and roles here.

## Acknowledgements

Built for the Ylookup × Encode Rebuild Private Markets AI Hackathon using the anonymised interviews and fund-operation datasets supplied by Ylookup.
