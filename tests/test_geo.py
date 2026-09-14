"""Tests for the geo-map aggregation pipeline.

The pure merge/aggregate helpers run without InfluxDB; the route test
injects a fake storage so the full endpoint behavior (naming, sorting,
degradation) is verified end-to-end.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient


def test_aggregate_geo_sent():
    """Per-(country, ip) rows must fold into bytes + unique IP counts."""
    from flowsight.storage.influxdb import _aggregate_geo_sent

    rows = [
        {"src_country_code": "US", "src_ip": "1.1.1.1", "_value": 100},
        {"src_country_code": "US", "src_ip": "2.2.2.2", "_value": 50},
        {"src_country_code": "US", "src_ip": "1.1.1.1", "_value": 25},
        {"src_country_code": "DE", "src_ip": "3.3.3.3", "_value": 10},
    ]
    sent = _aggregate_geo_sent(rows)

    by_code = {r["country_code"]: r for r in sent}
    assert by_code["US"]["bytes"] == 175
    assert by_code["US"]["unique_ips"] == 2
    assert by_code["DE"]["bytes"] == 10
    assert by_code["DE"]["unique_ips"] == 1


def test_merge_geo_rows():
    """Sent and received aggregates must merge and sort by total bytes."""
    from flowsight.storage.influxdb import _merge_geo_rows

    sent = [
        {"country_code": "US", "bytes": 100, "flows": 10, "unique_ips": 3},
        {"country_code": "DE", "bytes": 50, "flows": 5, "unique_ips": 2},
    ]
    received = [
        {"country_code": "US", "bytes": 20},
        {"country_code": "FR", "bytes": 500},
    ]

    merged = _merge_geo_rows(sent, received)

    assert [m["country_code"] for m in merged] == ["FR", "US", "DE"]
    us = merged[1]
    assert us["bytes_sent"] == 100
    assert us["bytes_received"] == 20
    assert us["flows"] == 10
    assert us["unique_ips"] == 3
    fr = merged[0]
    assert fr["bytes_sent"] == 0
    assert fr["bytes_received"] == 500
    assert fr["flows"] == 0
    assert fr["unique_ips"] == 0


class GeoFakeStorage:
    """Fake storage returning a fixed geo distribution."""

    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows

    async def get_geo_distribution(self, start: str, stop: str) -> list[dict[str, Any]]:
        return self.rows


@pytest.fixture
def geo_client():
    """TestClient wired to a fake storage with known geo rows."""
    from flowsight.api import deps
    from flowsight.api.main import app

    deps.storage = GeoFakeStorage(
        [
            {
                "country_code": "US",
                "bytes_sent": 100,
                "bytes_received": 20,
                "flows": 10,
                "unique_ips": 3,
            },
            {
                "country_code": "ZZ",
                "bytes_sent": 5,
                "bytes_received": 900,
                "flows": 2,
                "unique_ips": 1,
            },
        ]
    )
    client = TestClient(app)
    yield client
    deps.storage = None


def test_geo_map_route_uses_storage(geo_client):
    """GET /geo-map must return storage data with country names applied."""
    response = geo_client.get(
        "/api/v1/geo-map", params={"start": "2020-01-01T00:00:00Z", "stop": "2020-01-01T01:00:00Z"}
    )
    assert response.status_code == 200

    locations = response.json()["locations"]
    assert len(locations) == 2

    # Sorted by total bytes: ZZ (905) before US (120)
    assert locations[0]["country_code"] == "ZZ"
    assert locations[1]["country_code"] == "US"
    assert locations[1]["country_name"] == "United States"
    assert locations[1]["bytes_sent"] == 100
    assert locations[1]["bytes_received"] == 20
    assert locations[1]["flows"] == 10
    assert locations[1]["unique_ips"] == 3

    # Unknown codes keep the code as the name
    assert locations[0]["country_name"] == "ZZ"


def test_geo_map_route_requires_storage():
    """GET /geo-map must 503 when storage is not initialized."""
    from flowsight.api import deps
    from flowsight.api.main import app

    deps.storage = None
    client = TestClient(app)
    response = client.get(
        "/api/v1/geo-map", params={"start": "2020-01-01T00:00:00Z", "stop": "2020-01-01T01:00:00Z"}
    )
    assert response.status_code == 503
