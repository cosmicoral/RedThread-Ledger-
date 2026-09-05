import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
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
