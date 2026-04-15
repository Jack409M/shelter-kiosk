from __future__ import annotations


def test_health_live_returns_ok(client):
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == {"status": "ok"}


def test_health_ready_returns_ok(client):
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == {"status": "ok"}
