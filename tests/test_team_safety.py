"""
Smoke + behavior tests for the Team Leader + Safety module.

Run with:  python -m pytest tests/test_team_safety.py -v
or simply: python tests/test_team_safety.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from app.main import app
from app.services import team_safety_service as svc


def _client():
    # Reset the in-memory store to a known state for deterministic tests.
    svc.seed_sample_data(force=True)
    return TestClient(app)


def test_pages_render():
    c = _client()
    for path in ["/team/dashboard", "/team/manage", "/team/sos", "/safety"]:
        r = c.get(path)
        assert r.status_code == 200, path
        assert "text/html" in r.headers["content-type"]


def test_dashboard_stats_shape():
    c = _client()
    r = c.get("/api/team/dashboard")
    assert r.status_code == 200
    data = r.json()
    assert set(data["stats"]) == {
        "total_members", "checked_in", "requiring_attention", "active_sos"
    }
    assert data["stats"]["total_members"] == 4  # seeded members
    assert isinstance(data["recent_alerts"], list)
    assert isinstance(data["team_overview"], list)


def test_members_listing_and_filter():
    c = _client()
    r = c.get("/api/team/members")
    assert r.status_code == 200
    members = r.json()["members"]
    assert len(members) == 4

    # Filter by Safe
    r = c.get("/api/team/members", params={"status": "Safe"})
    safe = r.json()["members"]
    assert all(m["status"] == "Safe" for m in safe)

    # Invalid filter -> 400
    r = c.get("/api/team/members", params={"status": "Nonsense"})
    assert r.status_code == 400


def test_check_in_sets_safe():
    c = _client()
    r = c.post("/api/team/check-in", json={"participant_name": "Bob Lim", "location": "Hotel"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "Safe"
    assert body["location"] == "Hotel"
    assert body["last_check_in"] is not None


def test_check_in_unknown_member_404():
    c = _client()
    r = c.post("/api/team/check-in", json={"participant_name": "Nobody Here"})
    assert r.status_code == 404


def test_sos_workflow_end_to_end():
    c = _client()

    # Baseline active SOS count.
    before = c.get("/api/team/dashboard").json()["stats"]["active_sos"]

    # Participant submits an SOS.
    r = c.post("/api/team/sos", json={
        "participant_name": "Charlie Ng",
        "location": "Food Court",
        "message": "Need help",
    })
    assert r.status_code == 200
    alert = r.json()
    assert alert["status"] == "New"
    alert_id = alert["id"]

    # Member now shows SOS Active.
    members = c.get("/api/team/members").json()["members"]
    charlie = next(m for m in members if m["name"] == "Charlie Ng")
    assert charlie["status"] == "SOS Active"

    # Dashboard active count increased and alert appears in recent.
    dash = c.get("/api/team/dashboard").json()
    assert dash["stats"]["active_sos"] == before + 1
    assert any(a["id"] == alert_id for a in dash["recent_alerts"])

    # Leader marks In Progress.
    r = c.patch(f"/api/team/alerts/{alert_id}/status", json={"status": "In Progress"})
    assert r.status_code == 200
    assert r.json()["status"] == "In Progress"

    # Leader resolves. Member should drop back to Pending Check-in.
    r = c.patch(f"/api/team/alerts/{alert_id}/status", json={"status": "Resolved"})
    assert r.status_code == 200
    assert r.json()["status"] == "Resolved"

    members = c.get("/api/team/members").json()["members"]
    charlie = next(m for m in members if m["name"] == "Charlie Ng")
    assert charlie["status"] == "Pending Check-in"

    # Resolved alert appears in history.
    history = c.get("/api/team/alerts/history").json()["alerts"]
    assert any(a["id"] == alert_id for a in history)


def test_update_unknown_alert_404():
    c = _client()
    r = c.patch("/api/team/alerts/does-not-exist/status", json={"status": "Resolved"})
    assert r.status_code == 404


def test_invalid_alert_status_400():
    c = _client()
    r = c.post("/api/team/sos", json={"participant_name": "Alice Tan"})
    alert_id = r.json()["id"]
    r = c.patch(f"/api/team/alerts/{alert_id}/status", json={"status": "Bogus"})
    assert r.status_code == 400


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
