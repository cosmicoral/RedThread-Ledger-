import re
from pathlib import Path

from reference.constants import ALLOWED_SHEETS

BACKEND = Path(__file__).resolve().parents[2] / "backend"
REPO = BACKEND.parent
ALLOWED_MENTION_FILES = {"constants.py"}


def test_backend_does_not_name_ground_truth_sheets() -> None:
    offenders: list[str] = []
    for path in BACKEND.rglob("*.py"):
        if path.name in ALLOWED_MENTION_FILES:
            continue
        text = path.read_text()
        if "Staging Sheet" in text or re.search(r"\bDIU\b", text):
            offenders.append(str(path.relative_to(BACKEND)))
    assert offenders == []


def test_committed_reference_csvs_are_allowlisted_only() -> None:
    root = REPO / "data" / "hackathon" / "reference-data"
    csvs = sorted(path.name for path in root.glob("*.csv"))
    if not csvs:
        return
    assert set(csvs) <= set(ALLOWED_SHEETS.values())
    for name in csvs:
        assert "staging" not in name.lower()
        assert "diu" not in name.lower()
