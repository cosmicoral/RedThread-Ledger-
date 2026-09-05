from pathlib import Path

FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"


def test_frontend_uses_relative_api_prefix() -> None:
    api = (FRONTEND_SRC / "api.ts").read_text()
    assert 'export const API_BASE = "/api"' in api
    assert "localhost" not in api


def test_frontend_src_does_not_embed_localhost_hosts() -> None:
    offenders: list[str] = []
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        text = path.read_text()
        if "localhost:8000" in text or "http://localhost" in text or "https://localhost" in text:
            offenders.append(str(path.relative_to(FRONTEND_SRC)))
    assert offenders == []
