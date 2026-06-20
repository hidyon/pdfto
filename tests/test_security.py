"""Tests for API key auth and rate limiting."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import settings
from app.jobs import JobManager
from app.security import RateLimiter
from app.storage import Storage


@pytest.fixture
def client(tmp_path, monkeypatch):
    store = Storage(tmp_path)
    monkeypatch.setattr(main, "storage", store)
    monkeypatch.setattr(main, "jobs", JobManager(max_workers=1, db=store.db))
    monkeypatch.setattr(main, "rate_limiter", RateLimiter())
    return TestClient(main.app)


# -- RateLimiter unit ------------------------------------------------------- #
def test_rate_limiter_allows_within_limit():
    rl = RateLimiter()
    for _ in range(3):
        allowed, _ = rl.check("id", limit=3, window=60)
        assert allowed


def test_rate_limiter_blocks_over_limit():
    rl = RateLimiter()
    rl.check("id", 1, 60)
    allowed, retry = rl.check("id", 1, 60)
    assert not allowed
    assert retry > 0


def test_rate_limiter_disabled_when_limit_zero():
    rl = RateLimiter()
    for _ in range(100):
        allowed, _ = rl.check("id", limit=0, window=60)
        assert allowed


# -- auth ------------------------------------------------------------------- #
def test_auth_disabled_by_default_is_open(client):
    # No keys configured -> not 401 (unknown doc gives 404).
    r = client.get("/api/v1/documents/nope")
    assert r.status_code == 404


def test_missing_key_is_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "api_keys", {"secret"})
    r = client.get("/api/v1/documents/nope")
    assert r.status_code == 401
    assert r.json()["request_id"]
    assert r.headers.get("X-Request-ID")


def test_wrong_key_is_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "api_keys", {"secret"})
    r = client.get("/api/v1/documents/nope", headers={"X-API-Key": "nope"})
    assert r.status_code == 401


def test_valid_key_via_header_and_bearer(client, monkeypatch):
    monkeypatch.setattr(settings, "api_keys", {"secret"})
    r = client.get("/api/v1/documents/nope", headers={"X-API-Key": "secret"})
    assert r.status_code == 404  # past auth, doc just doesn't exist
    r = client.get("/api/v1/documents/nope",
                   headers={"Authorization": "Bearer secret"})
    assert r.status_code == 404


def test_health_open_even_with_auth(client, monkeypatch):
    monkeypatch.setattr(settings, "api_keys", {"secret"})
    assert client.get("/api/health").status_code == 200


# -- rate limit (via API) --------------------------------------------------- #
def test_rate_limit_returns_429(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit", 2)
    monkeypatch.setattr(settings, "rate_window_seconds", 60)
    assert client.get("/api/v1/documents/x").status_code == 404
    assert client.get("/api/v1/documents/x").status_code == 404
    r = client.get("/api/v1/documents/x")
    assert r.status_code == 429
    assert r.headers.get("Retry-After")
