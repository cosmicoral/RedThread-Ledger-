from pathlib import Path

import pytest

from reference.constants import ALLOWED_SHEETS, FORBIDDEN_SHEETS
from reference.loader import ForbiddenSheetError, load_reference_data, require_allowed_sheet

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "reference"


def test_account_map_has_seven_rows() -> None:
    data = load_reference_data(FIXTURE_DIR)
    assert len(data["Account Map"]) == 7
    assert data["Account Map"][0]["Account Number"] == "240-149813-030"


@pytest.mark.parametrize("sheet", sorted(FORBIDDEN_SHEETS))
def test_loader_rejects_ground_truth_sheets(sheet: str) -> None:
    with pytest.raises(ForbiddenSheetError):
        require_allowed_sheet(sheet)


def test_loader_rejects_unknown_sheet() -> None:
    with pytest.raises(ForbiddenSheetError):
        require_allowed_sheet("Upload Template")


def test_allowlist_covers_runtime_inputs_only() -> None:
    assert "Account Map" in ALLOWED_SHEETS
    assert "Legal Entity Master List" in ALLOWED_SHEETS
    for name in FORBIDDEN_SHEETS:
        assert name not in ALLOWED_SHEETS
