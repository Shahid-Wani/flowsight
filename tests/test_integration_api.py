"""API-level integration tests: routes + real InfluxDB end-to-end.

Route tests elsewhere inject fake storage and the storage suite
exercises storage methods directly - neither catches bugs that live in
the route -> normalizer -> Flux path. The bare-``now`` bug (the
dashboard's ``stop=now`` was invalid Flux) hid exactly there for days:
every dashboard query against a real InfluxDB failed while all
fake-storage tests stayed green.

This suite wires a real ``InfluxDBStorage`` into the API's dependency
(``deps.storage`` - what the endpoints actually resolve) and hits the
endpoints with TestClient, including the dashboard's exact query
forms.

Skipped unless an authenticated InfluxDB is reachable (CI provides
one via a service container). Writes go to synthetic time windows
(T0+600 and later) that are disjoint from the storage suite
(T0..T0+361), so the two suites never interfere regardless of order.
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from test_integration_influxdb import (
    INFLUX_BUCKET,
    INFLUX_ORG,
    INFLUX_TOKEN,
    INFLUX_URL,
    T0,
    _influx_available,
    _rfc3339,
    make_flow,
)

from flowsight import settings
from flowsight.storage.influxdb import InfluxDBStorage

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _influx_available(), reason=f"InfluxDB not reachable at {INFLUX_URL}"),
]


@pytest.fixture
def api_storage():
    """Real storage, connected and wired into the API dependency."""
    saved = (
        settings.storage.url,
        settings.storage.token,
        settings.storage.org,
        settings.storage.bucket,
    )
    settings.storage.url = INFLUX_URL
    settings.storage.token = INFLUX_TOKEN
    settings.storage.org = INFLUX_ORG
    settings.storage.bucket = INFLUX_BUCKET

    from flowsight.api import deps

    instance = InfluxDBStorage()
    asyncio.run(instance.connect())
    deps.storage = instance

    yield instance

    deps.storage = None
    asyncio.run(instance.disconnect())
    (
        settings.storage.url,
        settings.storage.token,
        settings.storage.org,
        settings.storage.bucket,
    ) = saved


def seed_and_wait(instance: InfluxDBStorage, flows):
    """Write flows and wait until they are queryable (sync wrapper)."""
    from test_integration_influxdb import write_and_wait

    asyncio.run(write_and_wait(instance, flows, count=len(flows)))


def make_client() -> TestClient:
    from flowsight.api.main import app

    return TestClient(app)


# The dashboard polls exactly these forms; every one must return 200
# through route + normalizer + real Flux (the bare-`now` bug class).
DASHBOARD_FORMS = [
    "/api/v1/flows",
    "/api/v1/top-talkers",
    "/api/v1/bandwidth",
    "/api/v1/protocols",
    "/api/v1/geo-map",
]


@pytest.mark.parametrize("endpoint", DASHBOARD_FORMS)
def test_dashboard_query_forms_end_to_end(api_storage, endpoint):
    """The dashboard's start=-1h&stop=now form must work on every endpoint."""
    client = make_client()
    response = client.get(endpoint, params={"start": "-1h", "stop": "now"})
    assert response.status_code == 200


def test_health(api_storage):
    """Health stays healthy with real storage wired."""
    client = make_client()
    response = client.get("/health")
    assert response.status_code == 200


def test_flows_endpoint_returns_seeded_pivoted_data(api_storage):
    """Seeded flows must come back pivoted: fields + tags as columns."""
    flows = [
        make_flow(
            T0 + 600,
            "10.1.0.1",
            "10.1.0.9",
            111,
            protocol=6,
            src_country_code="US",
            dst_country_code="DE",
        ),
        make_flow(
            T0 + 601,
            "10.1.0.2",
            "10.1.0.9",
            222,
            protocol=17,
            src_country_code="US",
            dst_country_code="US",
        ),
        make_flow(
            T0 + 602,
            "10.1.0.1",
            "10.1.0.9",
            333,
            protocol=6,
            src_country_code="US",
            dst_country_code="DE",
        ),
    ]
    seed_and_wait(api_storage, flows)

    client = make_client()
    response = client.get(
        "/api/v1/flows", params={"start": _rfc3339(T0 + 599), "stop": _rfc3339(T0 + 660)}
    )
    assert response.status_code == 200

    flows_out = response.json()["flows"]
    assert len(flows_out) == 3
    first = flows_out[0]
    assert first["src_ip"] in ("10.1.0.1", "10.1.0.2")
    assert "bytes" in first and "packets" in first
    assert "_field" not in first and "_value" not in first


def test_top_talkers_endpoint_aggregates(api_storage):
    """Top talkers must aggregate per source IP and sort by bytes."""
    flows = [
        make_flow(T0 + 620, "10.1.1.1", "10.1.1.9", 100),
        make_flow(T0 + 621, "10.1.1.1", "10.1.1.9", 150),
        make_flow(T0 + 622, "10.1.1.2", "10.1.1.9", 500),
    ]
    seed_and_wait(api_storage, flows)

    client = make_client()
    response = client.get(
        "/api/v1/top-talkers", params={"start": _rfc3339(T0 + 619), "stop": _rfc3339(T0 + 660)}
    )
    assert response.status_code == 200

    talkers = response.json()["talkers"]
    assert talkers[0]["src_ip"] == "10.1.1.1"
    assert talkers[0]["value"] == 250
    assert talkers[1]["value"] == 500


def test_protocols_endpoint_returns_names(api_storage):
    """The route must map protocol numbers to display names."""
    flows = [
        make_flow(T0 + 640, "10.1.2.1", "10.1.2.9", 300, protocol=6),
        make_flow(T0 + 641, "10.1.2.2", "10.1.2.9", 100, protocol=6),
        make_flow(T0 + 642, "10.1.2.3", "10.1.2.9", 400, protocol=17),
    ]
    seed_and_wait(api_storage, flows)

    client = make_client()
    response = client.get(
        "/api/v1/protocols", params={"start": _rfc3339(T0 + 639), "stop": _rfc3339(T0 + 660)}
    )
    assert response.status_code == 200

    dist = {row["protocol"]: row["bytes"] for row in response.json()["distribution"]}
    assert dist.get("TCP") == 400
    assert dist.get("UDP") == 400


def test_geo_map_endpoint_names_and_sorts(api_storage):
    """Geo-map must apply country names and sort by total bytes."""
    flows = [
        make_flow(
            T0 + 650, "1.1.1.1", "9.9.9.9", 111, src_country_code="US", dst_country_code="DE"
        ),
        make_flow(
            T0 + 651, "2.2.2.2", "8.8.8.8", 222, src_country_code="US", dst_country_code="US"
        ),
        make_flow(
            T0 + 652, "1.1.1.1", "7.7.7.7", 333, src_country_code="US", dst_country_code="DE"
        ),
    ]
    seed_and_wait(api_storage, flows)

    client = make_client()
    response = client.get(
        "/api/v1/geo-map", params={"start": _rfc3339(T0 + 649), "stop": _rfc3339(T0 + 660)}
    )
    assert response.status_code == 200

    locations = response.json()["locations"]
    assert [loc["country_code"] for loc in locations] == ["US", "DE"]

    us = locations[0]
    assert us["country_name"] == "United States"
    assert us["bytes_sent"] == 666
    assert us["bytes_received"] == 222
    assert us["flows"] == 3
    assert us["unique_ips"] == 2

    de = locations[1]
    assert de["country_name"] == "Germany"
    assert de["bytes_received"] == 444


def make_enriched_flow(
    unix_secs: int,
    src_ip: str,
    dst_ip: str,
    bytes_: int,
    protocol: int,
    country: str,
    asn: int,
    asn_org: str,
) -> dict:
    """Flow with full enrichment (Day 7: asn_org is now a tag too)."""
    return make_flow(
        unix_secs,
        src_ip,
        dst_ip,
        bytes_,
        protocol=protocol,
        src_country_code=country,
        dst_country_code=country,
    ) | {"src_asn": asn, "src_asn_org": asn_org}


def test_top_talkers_end_to_end_enriched(api_storage):
    """Talkers must come back with packets/protocol/country/asn populated."""
    flows = [
        make_enriched_flow(
            T0 + 700,
            "10.2.0.1",
            "10.2.0.9",
            100,
            protocol=6,
            country="US",
            asn=15169,
            asn_org="GOOGLE",
        ),
        make_enriched_flow(
            T0 + 701,
            "10.2.0.1",
            "10.2.0.9",
            400,
            protocol=17,
            country="US",
            asn=15169,
            asn_org="GOOGLE",
        ),
        make_enriched_flow(
            T0 + 702, "10.2.0.2", "10.2.0.9", 50, protocol=6, country="DE", asn=3320, asn_org="DTAG"
        ),
    ]
    seed_and_wait(api_storage, flows)

    client = make_client()
    response = client.get(
        "/api/v1/top-talkers", params={"start": _rfc3339(T0 + 699), "stop": _rfc3339(T0 + 760)}
    )
    assert response.status_code == 200

    talkers = response.json()["talkers"]
    assert len(talkers) == 2

    first = talkers[0]  # 10.2.0.1 with 500 total bytes
    assert first["src_ip"] == "10.2.0.1"
    assert first["value"] == 500
    assert first["packets"] == (100 // 500) + (400 // 500) + 2  # make_flow packets + this flow's
    assert first["protocol"] == 17  # dominant (400-byte) row's protocol, as a number
    assert first["country_code"] == "US"
    assert first["asn"] == 15169
    assert first["asn_org"] == "GOOGLE"
    assert first["dst_ip"] == "10.2.0.9"


def test_alert_persistence_round_trip_via_api(api_storage):
    """Pipeline-persisted alerts must be readable and ackable via the API."""

    from flowsight.alerting.threshold import Alert
    from flowsight.storage.influxdb import alert_to_point

    alert_time = datetime.now(tz=timezone.utc) - timedelta(minutes=5)
    alert = Alert(
        rule_name="persisted_rule",
        severity="warning",
        message="persisted alert round trip",
        flow_data={"src_ip": "10.2.9.9", "bytes": 12345},
        timestamp=alert_time,
    )
    asyncio.run(api_storage.write_flows([]))  # ensure connected

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(
            api_storage.write_api.write(
                bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=[alert_to_point(alert)]
            )
        )
    finally:
        loop.close()

    # Poll until the alert is readable through the API route
    client = make_client()
    found = None
    for _ in range(30):
        response = client.get("/api/v1/alerts", params={"start": "-15m", "stop": "now"})
        assert response.status_code == 200
        matches = [a for a in response.json()["alerts"] if a["id"] == alert.id]
        if matches:
            found = matches[0]
            break

        time.sleep(0.5)
    assert found is not None, "persisted alert never became readable via the API"
    assert found["rule_name"] == "persisted_rule"
    assert found["severity"] == "warning"
    assert found["flow_data"]["bytes"] == 12345
    assert found["acknowledged"] is False

    # Acknowledge through the API, then verify the ack state persists
    ack = client.post(
        f"/api/v1/alerts/{alert.id}/acknowledge", params={"acknowledged_by": "ci-bot"}
    )
    assert ack.status_code == 200

    acked = None
    for _ in range(30):
        response = client.get(
            "/api/v1/alerts", params={"start": "-15m", "stop": "now", "acknowledged": "true"}
        )
        assert response.status_code == 200
        matches = [a for a in response.json()["alerts"] if a["id"] == alert.id]
        if matches:
            acked = matches[0]
            break
        time.sleep(0.5)
    assert acked is not None, "ack state never became visible via the API"
    assert acked["acknowledged"] is True
    assert acked["acknowledged_by"] == "ci-bot"
