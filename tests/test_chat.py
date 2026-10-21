from fastapi.testclient import TestClient

from app.main import app


def test_vercel_entrypoint_and_ui():
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "The Hive" in response.text


def test_supabase_config_requires_environment(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    with TestClient(app) as client:
        response = client.get("/api/config")
        assert response.status_code == 503


def test_supabase_config_returns_only_public_values(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co/")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_do_not_return")
    with TestClient(app) as client:
        response = client.get("/api/config")
        assert response.status_code == 200
        assert response.json() == {
            "supabaseUrl": "https://example.supabase.co",
            "supabaseKey": "sb_publishable_test",
        }
