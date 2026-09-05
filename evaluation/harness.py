"""Evaluate pipeline output against held-out statements.

Usage:
    make eval
"""

from __future__ import annotations

from collections import defaultdict

from evaluation.compare import _amount, _norm, index_staging
from evaluation.metrics import METRIC_AREAS
from evaluation.workbook import load_ground_truth
from runtime import process_all


def _attr(item, name: str) -> str:
    value = getattr(item, name, None)
    return "" if value is None else str(value)


def run() -> dict[str, object]:
    truth = load_ground_truth()
    staging = truth["staging"]
    journals = truth["journals"]
    predicted = process_all()

    if not staging:
        print("No ground-truth workbook found. Run make sync-data first.")
        return {area: "skipped" for area in METRIC_AREAS}

    by_key = index_staging(staging)
    tallies: dict[str, list[bool]] = defaultdict(list)
    unmatched_truth = 0
    correct_review_for_unmatched = 0

    for item in predicted:
        key = (
            item.evidence.account_number or "",
            item.evidence.bank_reference or "",
            _amount(item.amount),
        )
        row = by_key.get(key)
        if row is None:
            # bank reference NONREF can collide; try amount + account only
            row = next(
                (
                    candidate
                    for candidate_key, candidate in by_key.items()
                    if candidate_key[0] == key[0]
                    and candidate_key[2] == key[2]
                    and (
                        _norm(candidate.get("Narrative")) in _norm(item.evidence.narrative)
                        or _norm(item.evidence.narrative) in _norm(candidate.get("Narrative"))
                    )
                ),
                None,
            )
        if row is None:
            continue

        tallies["statement_extraction"].append(
            item.currency == row.get("Currency") and _amount(item.amount) == _amount(
                row.get("Debit amount") or row.get("Credit amount")
            )
        )
        truth_cp = row.get("Matched Sender/Beneficiary", "")
        pred_cp = _attr(item, "counterparty")
        if not truth_cp:
            unmatched_truth += 1
            if item.status.value == "needs_review" or not pred_cp:
                correct_review_for_unmatched += 1
            tallies["counterparty_resolution"].append(not pred_cp)
        else:
            tallies["counterparty_resolution"].append(_norm(pred_cp) == _norm(truth_cp))

        if row.get("Matched Project Code", "").startswith("Flag for review"):
            tallies["project_resolution"].append(item.project_code in (None, "", "OH - Bank Fees"))
        elif row.get("Matched Project Code"):
            tallies["project_resolution"].append(
                _norm(item.project_code) == _norm(row.get("Matched Project Code"))
            )

        if row.get("Classification"):
            tallies["classification"].append(
                _norm(item.classification) == _norm(row.get("Classification"))
            )
        if row.get("Resolved Position"):
            tallies["position_resolution"].append(
                _norm(item.position) == _norm(row.get("Resolved Position"))
            )
        tallies["accounting_validity"].append(
            len(item.journal_lines) == 2
            and round(sum(line.debit for line in item.journal_lines), 2)
            == round(sum(line.credit for line in item.journal_lines), 2)
        )
        tallies["evidence"].append(bool(item.evidence.document_name and item.evidence.page))
        if row.get("Classification") == "Review" or not truth_cp:
            tallies["exception_handling"].append(item.status.value == "needs_review" or not pred_cp)

    tallies["journal_generation"].append(len(journals) == 2 * len(staging) if staging else False)

    print("RedThread Ledger evaluation")
    print(f"Predicted {len(predicted)} transactions against {len(staging)} staging rows")
    print()
    summary: dict[str, object] = {}
    for area in METRIC_AREAS:
        values = tallies.get(area, [])
        if not values:
            summary[area] = "n/a"
            print(f"  {area}: n/a")
            continue
        rate = sum(values) / len(values)
        summary[area] = round(rate, 3)
        print(f"  {area}: {rate:.1%} ({sum(values)}/{len(values)})")
    if unmatched_truth:
        print(
            f"  unmatched counterparties left unresolved or in review: "
            f"{correct_review_for_unmatched}/{unmatched_truth}"
        )
    return summary


if __name__ == "__main__":
    run()
