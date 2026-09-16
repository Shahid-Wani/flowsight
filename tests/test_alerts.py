"""Tests for alert identity and acknowledgement.

Regression guard: alert IDs used to be enumeration indexes over the
FILTERED alert list while acknowledgement indexed the UNFILTERED
history - acknowledging an alert fetched with filters hit the wrong
record (or none).
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from flowsight.alerting.threshold import AlertSeverity, ThresholdRule


@pytest.fixture
def alert_client():
    """TestClient with a fresh alert manager containing known alerts."""
    import flowsight.alerting.manager as am

    previous = am._alert_manager
    am._alert_manager = None

    manager = asyncio.run(am.get_alert_manager())
    for name, severity, threshold in (
        ("smoke_warn", AlertSeverity.WARNING, 100),
        ("smoke_crit", AlertSeverity.CRITICAL, 1000),
    ):
        manager.add_custom_rule(
            ThresholdRule(
                name=name,
                field="bytes",
                operator=">",
                value=threshold,
                severity=severity,
                cooldown_seconds=0,
            )
        )

    asyncio.run(manager.evaluate_flow({"src_ip": "10.0.0.1", "bytes": 500, "packets": 1}))
    asyncio.run(manager.evaluate_flow({"src_ip": "10.0.0.2", "bytes": 600, "packets": 1}))
    asyncio.run(manager.evaluate_flow({"src_ip": "10.0.0.3", "bytes": 5000, "packets": 1}))

    from flowsight.api.main import app

    client = TestClient(app)

    yield client, manager

    am._alert_manager = previous


def test_alerts_have_stable_unique_ids(alert_client):
    """Each alert must expose a unique stable id."""
    client, _manager = alert_client
    response = client.get("/api/v1/alerts", params={"start": "-1h", "stop": "now"})
    assert response.status_code == 200

    alerts = response.json()["alerts"]
    assert len(alerts) == 4  # 3 warnings + 1 critical
    severity_counts = {}
    for alert in alerts:
        severity_counts[alert["severity"]] = severity_counts.get(alert["severity"], 0) + 1
    assert severity_counts == {"warning": 3, "critical": 1}

    ids = [a["id"] for a in alerts]
    assert len(set(ids)) == 4
    assert all(isinstance(i, str) and i for i in ids)


def test_acknowledge_after_filter_hits_the_right_alert(alert_client):
    """Acknowledging an id fetched through a filter must hit that alert."""
    client, _manager = alert_client

    filtered = client.get(
        "/api/v1/alerts", params={"start": "-1h", "stop": "now", "severity": "critical"}
    )
    assert filtered.status_code == 200
    critical = filtered.json()["alerts"]
    assert len(critical) == 1
    target_id = critical[0]["id"]

    ack = client.post(f"/api/v1/alerts/{target_id}/acknowledge")
    assert ack.status_code == 200
    assert ack.json()["success"] is True

    all_alerts = client.get("/api/v1/alerts", params={"start": "-1h", "stop": "now"}).json()
    acked = [a for a in all_alerts["alerts"] if a["acknowledged"]]
    assert len(acked) == 1
    assert acked[0]["id"] == target_id
    assert acked[0]["rule_name"] == "smoke_crit"


def test_acknowledge_unknown_id_returns_404(alert_client):
    """An unknown alert id must 404, not acknowledge a random alert."""
    client, _manager = alert_client
    response = client.post("/api/v1/alerts/does-not-exist/acknowledge")
    assert response.status_code == 404
