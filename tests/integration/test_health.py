from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "transactions" in body
    assert client.get("/api/health").json() == body


def test_queue_shape() -> None:
    response = client.get("/api/queue")
    assert response.status_code == 200
    body = response.json()
    assert "ready_to_post" in body
    assert "needs_review" in body
    assert "counts" in body
    assert body["total"] == len(body["ready_to_post"]) + len(body["needs_review"])


def test_unknown_statement_is_404() -> None:
    response = client.get("/api/statements/not-a-real-file.pdf")
    assert response.status_code == 404
