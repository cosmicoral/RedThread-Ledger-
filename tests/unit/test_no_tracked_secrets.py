import re
import subprocess
from pathlib import Path

from settings import settings

ROOT = Path(__file__).resolve().parents[2]

SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile("GEMINI_API_KEY=" + r"[^\s#]+"),
)


def _tracked_text_files() -> list[Path]:
    files = [ROOT / ".env.example"]
    skip = {".venv", "node_modules", "__pycache__", "tests"}
    for path in (ROOT / "backend").rglob("*"):
        if any(part in skip for part in path.parts):
            continue
        if path.is_file() and path.suffix in {".py", ".md", ".txt", ".yml", ".yaml", ".example"}:
            files.append(path)
    for path in (ROOT / "frontend" / "src").rglob("*"):
        if path.is_file() and path.suffix in {".ts", ".tsx", ".css"}:
            files.append(path)
    for extra in (ROOT / "README.md", ROOT / "deploy" / "README.md", ROOT / ".env.example"):
        files.append(extra)
    return files


def test_agent_defaults_are_safe() -> None:
    assert settings.agent_enabled is False
    assert settings.gemini_api_key == ""
    assert settings.agent_max_tool_rounds == 4
    assert settings.agent_timeout_seconds > 0


def test_env_example_has_empty_key_placeholder() -> None:
    text = (ROOT / ".env.example").read_text()
    assert "AGENT_ENABLED=false" in text
    assert "GEMINI_API_KEY=\n" in text or text.strip().endswith("GEMINI_API_KEY=")
    assert not re.search(r"GEMINI_API_KEY=.+", text)
    assert "GEMINI_MODEL=gemini-3.6-flash" in text


def test_tracked_sources_have_no_secret_like_values() -> None:
    offenders: list[str] = []
    for path in _tracked_text_files():
        if not path.is_file() or ".venv" in path.parts or "node_modules" in path.parts:
            continue
        text = path.read_text(errors="ignore")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                offenders.append(f"{path.relative_to(ROOT)}:{pattern.pattern}")
    assert offenders == []


def test_dotenv_is_not_a_tracked_secret_file() -> None:
    gitignore = (ROOT / ".gitignore").read_text()
    assert ".env" in gitignore.splitlines() or gitignore.startswith(".env")
    tracked = subprocess.check_output(
        ["git", "ls-files", "--", ".env"],
        cwd=ROOT,
        text=True,
    )
    assert tracked.strip() == ""
