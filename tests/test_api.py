import pytest
from fastapi.testclient import TestClient
from sales_intelligence.analytics import analyze, export_csv
from sales_intelligence.api import app, attempts

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "test-only-password-never-deploy")
    monkeypatch.setenv("SESSION_SECRET", "test-only-signing-key-never-deploy-12345")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.delenv("CALLS_ANNOTATIONS_PATH", raising=False)
    monkeypatch.delenv("CALLS_ANNOTATIONS_JSON", raising=False)
    attempts.clear()
    return TestClient(app)

HEADERS = {"X-Sales-Client": "web", "Content-Type": "text/csv", "X-File-Name": "test.csv"}

def sign_in(client):
    return client.post("/api/login", json={"password": "test-only-password-never-deploy"}, headers={"X-Sales-Client": "web"})

def test_upload_private_and_same_core(client, csv_data):
    assert client.post("/api/analyze", content=csv_data, headers=HEADERS).status_code == 401
    response = sign_in(client)
    assert response.status_code == 200
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=strict" in response.headers["set-cookie"].lower()
    r = client.post("/api/analyze", content=csv_data, headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == analyze(csv_data)
    assert r.headers["cache-control"] == "no-store"
    exported = client.post("/api/export", content=csv_data, headers=HEADERS)
    assert exported.content == export_csv(analyze(csv_data))
    assert client.post("/api/logout", headers={"X-Sales-Client": "web"}).status_code == 200
    assert client.get("/api/calls").status_code == 401

def test_csrf_and_invalid_files(client):
    assert client.post("/api/login", json={"password": "x"}).status_code == 403
    assert client.post("/api/login", json={"password": "x"}, headers={"X-Sales-Client": "web", "Origin": "https://evil.invalid"}).status_code == 403
    sign_in(client)
    assert client.post("/api/analyze", content="garbage", headers=HEADERS).status_code == 422
    assert client.post("/api/analyze", content="garbage", headers={**HEADERS, "X-File-Name": "a.exe"}).status_code == 422

def test_public_demo_has_no_valid_phones(client):
    report = client.get("/api/demo").json()
    assert report["demo"]
    assert len(report["report"]["rows"]) == 8
    assert all(r["phone"].startswith("Контакт") for r in report["report"]["rows"])
    assert client.get("/api/demo/calls").json()["average"] == 57.95
    assert client.get("/api/calls").status_code == 401
    assert not client.get("/api/session").json()["authenticated"]

def test_unconfigured_fails_closed(client, monkeypatch):
    monkeypatch.delenv("APP_PASSWORD")
    assert sign_in(client).status_code == 503
    assert client.get("/api/calls").status_code == 401

def test_bad_cookie_and_rate_limit(client):
    client.cookies.set("si_session", "0.bad.bad")
    assert client.get("/api/calls").status_code == 401
    for _ in range(8):
        assert client.post("/api/login", json={"password": "wrong"}, headers={"X-Sales-Client": "web"}).status_code == 401
    assert sign_in(client).status_code == 429

def test_stream_limit(client):
    sign_in(client)
    response = client.post("/api/analyze", content=iter([b"a" * (1024*1024), b"b" * (1024*1024), b"c"]), headers=HEADERS)
    assert response.status_code == 422

def test_validation_does_not_echo_password(client):
    password = "sensitive" * 50
    response = client.post("/api/login", json={"password": password}, headers={"X-Sales-Client": "web"})
    assert response.status_code == 422
    assert password not in response.text

def test_chunked_login_size_limit(client):
    r = client.post("/api/login", content=iter([b" " * 4096, b" "]), headers={"X-Sales-Client": "web"})
    assert r.status_code == 413

def test_environment_calls_require_auth(client, monkeypatch):
    monkeypatch.setenv("CALLS_ANNOTATIONS_JSON", "[]")
    assert client.get("/api/calls").status_code == 401
    sign_in(client)
    assert client.get("/api/calls").json()["calls"] == []
    monkeypatch.setenv("CALLS_ANNOTATIONS_JSON", "invalid")
    assert client.get("/api/calls").status_code == 503
