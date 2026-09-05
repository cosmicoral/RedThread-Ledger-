from __future__ import annotations

from collections.abc import Iterable


def _norm(value: str | None) -> str:
    return " ".join((value or "").upper().split())


def _amount(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(abs(float(str(value).replace(",", ""))), 2)
    except ValueError:
        return None


def match_key(row: dict) -> tuple[str, str, float | None]:
    return (
        row.get("Account Number") or row.get("account_number") or "",
        row.get("Bank reference") or row.get("bank_reference") or "",
        _amount(row.get("Debit amount") or row.get("Credit amount") or row.get("amount")),
    )


def index_staging(rows: Iterable[dict]) -> dict[tuple[str, str, float | None], dict]:
    return {match_key(row): row for row in rows}


def score_extraction(predicted: dict, truth: dict) -> bool:
    return (
        _norm(predicted.get("bank_reference")) == _norm(truth.get("Bank reference"))
        and predicted.get("currency") == truth.get("Currency")
        and _amount(predicted.get("amount"))
        == _amount(truth.get("Debit amount") or truth.get("Credit amount"))
    )


def score_pair(pred, truth, pred_field: str, truth_field: str) -> bool:
    left = _norm(getattr(pred, pred_field, None) if not isinstance(pred, dict) else pred.get(pred_field))
    right = _norm(truth.get(truth_field))
    if not right:
        return True
    return left == right
