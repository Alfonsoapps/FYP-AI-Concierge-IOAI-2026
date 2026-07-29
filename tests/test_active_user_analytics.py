"""Focused tests for anonymous active-session analytics."""

import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import admin
from app.routers import chat


SESSION_A = "11111111-1111-4111-8111-111111111111"
SESSION_B = "22222222-2222-4222-8222-222222222222"


@pytest.fixture()
def isolated_analytics(monkeypatch, tmp_path):
    database = tmp_path / "analytics.db"
    monkeypatch.setattr(chat, "ANALYTICS_DB_PATH", database)
    chat.manager.active_connections.clear()
    chat._initialize_analytics()
    yield database
    chat.manager.active_connections.clear()


def _client() -> TestClient:
    test_app = FastAPI()
    test_app.include_router(chat.router)
    test_app.include_router(admin.router)
    return TestClient(test_app)


def test_duplicate_heartbeats_upsert_one_anonymous_session(isolated_analytics):
    chat.record_user_activity(SESSION_A, now=100.0)
    chat.record_user_activity(SESSION_A, now=120.0)

    assert chat.get_active_user_count(now=120.0) == 1
    with sqlite3.connect(isolated_analytics) as connection:
        rows = connection.execute(
            "SELECT user_id, last_seen FROM active_users"
        ).fetchall()
    assert rows == [(chat._session_hash(SESSION_A), 120.0)]
    assert SESSION_A not in rows[0][0]


def test_distinct_sessions_are_counted_once_each(isolated_analytics):
    chat.record_user_activity(SESSION_A, now=200.0)
    chat.record_user_activity(SESSION_B, now=200.0)

    assert chat.get_active_user_count(now=200.0) == 2


def test_sessions_expire_and_are_deleted_after_ttl(isolated_analytics):
    chat.record_user_activity(SESSION_A, now=300.0)

    assert chat.get_active_user_count(
        now=300.0 + chat.ACTIVE_USER_TTL_SECONDS + 0.001
    ) == 0
    with sqlite3.connect(isolated_analytics) as connection:
        assert connection.execute("SELECT COUNT(*) FROM active_users").fetchone()[0] == 0


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"session_id": "short"},
        {"session_id": "contains spaces and PII@example.com"},
        {"session_id": SESSION_A, "unexpected": True},
    ],
)
def test_activity_endpoint_rejects_malformed_payloads(isolated_analytics, payload):
    client = _client()
    response = client.post("/chat/activity", json=payload)

    assert response.status_code == 422
    assert chat.get_active_user_count() == 0


def test_activity_and_admin_analytics_response(
    isolated_analytics, monkeypatch
):
    async def fake_knowledge():
        return [{"id": "one"}, {"id": "two"}]

    monkeypatch.setattr(
        admin,
        "rag_db",
        SimpleNamespace(get_all_knowledge=fake_knowledge),
    )
    with sqlite3.connect(isolated_analytics) as connection:
        connection.execute(
            "UPDATE metrics SET value = 7 WHERE key = 'total_queries'"
        )

    client = _client()
    first = client.post("/chat/activity", json={"session_id": SESSION_A})
    duplicate = client.post("/chat/activity", json={"session_id": SESSION_A})
    analytics = client.get(
        "/api/v1/admin/analytics",
        headers={"x-user-role": "Organiser"},
    )

    assert first.status_code == duplicate.status_code == 200
    assert first.json() == {"status": "active"}
    assert analytics.status_code == 200
    assert analytics.headers["cache-control"] == "no-store, max-age=0"
    assert analytics.json() == {
        "total_queries": 7,
        "active_users": 1,
        "kb_size": 2,
        "system_health": "100% Online",
    }
