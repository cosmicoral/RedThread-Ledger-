from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IGNORE = (ROOT / ".gitignore").read_text()


def test_gitignore_excludes_secrets_and_caches() -> None:
    for token in (".env", ".venv/", "__pycache__/", "node_modules/", ".pytest_cache/"):
        assert token in IGNORE


def test_gitignore_keeps_evaluation_workbook_out() -> None:
    assert "data/raw/*" in IGNORE
    assert "*.xlsx" in IGNORE
