from __future__ import annotations

import csv
from pathlib import Path

from reference.constants import ALLOWED_SHEETS, FORBIDDEN_SHEETS


class ForbiddenSheetError(ValueError):
    """Raised when a ground-truth or non-allowlisted sheet is requested."""


def _canonical_sheet_name(name: str) -> str:
    return name.strip()


def require_allowed_sheet(name: str) -> str:
    canonical = _canonical_sheet_name(name)
    if canonical in FORBIDDEN_SHEETS:
        raise ForbiddenSheetError(f"Sheet {name!r} is not a runtime input")
    if canonical not in ALLOWED_SHEETS:
        raise ForbiddenSheetError(f"Sheet {name!r} is not in the reference allowlist")
    return canonical


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def load_reference_data(reference_dir: str | Path) -> dict[str, list[dict[str, str]]]:
    """Load allowlisted CSV extracts. Never opens the working workbook."""
    root = Path(reference_dir)
    loaded: dict[str, list[dict[str, str]]] = {}
    for sheet_name, filename in ALLOWED_SHEETS.items():
        require_allowed_sheet(sheet_name)
        path = root / filename
        if path.exists():
            loaded[sheet_name] = _read_csv(path)
        else:
            loaded[sheet_name] = []
    return loaded
