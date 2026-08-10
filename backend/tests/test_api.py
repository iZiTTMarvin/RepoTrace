from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def test_health(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("REPO_TRACE_DB_PATH", str(tmp_path / "test.db"))
    from app.core.config import get_settings

    get_settings.cache_clear()
    app = create_app()
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
