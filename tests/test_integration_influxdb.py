"""Integration tests against a real InfluxDB 2.x instance.

These tests exercise the real write/query round-trip (line protocol,
batching, Flux queries, geo aggregation). They are skipped unless an
InfluxDB instance is reachable - CI provides one via a service
container; locally they are skipped unless FLOWSIGHT_INFLUXDB_URL
points at a running instance.

Each test writes flows into its own synthetic time window (January
2020) so tests never interfere with each other regardless of execution
order or accumulated data.
"""

import asyncio
import os
from typing import Any

import pytest

from flowsight import settings
from flowsight.storage.influxdb import InfluxDBStorage

INFLUX_URL = os.environ.get("FLOWSIGHT_INFLUXDB_URL", "http://localhost:8086")
INFLUX_TOKEN = os.environ.get("FLOWSIGHT_INFLUXDB_TOKEN", "my-super-secret-admin-token")
INFLUX_ORG = os.environ.get("FLOWSIGHT_INFLUXDB_ORG", "flowsight")
INFLUX_BUCKET = os.environ.get("FLOWSIGHT_INFLUXDB_BUCKET", "flows")


def _influx_available() -> bool:
    """True if a compatible, authenticated InfluxDB is reachable."""
    try:
        from influxdb_client import InfluxDBClient

        with InfluxDBClient(
            url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=5000
        ) as client:
            client.buckets_api().find_buckets()
        return True
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _influx_available(), reason=f"InfluxDB not reachable at {INFLUX_URL}"),
]


@pytest.fixture
async def storage():
    """Connected storage with settings pointed at the test instance."""
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

    instance = InfluxDBStorage()
    await instance.connect()
    yield instance
    await instance.disconnect()

    (
        settings.storage.url,
        settings.storage.token,
        settings.storage.org,
        settings.storage.bucket,
    ) = saved


def make_flow(
    unix_secs: int,
    src_ip: str,
    dst_ip: str,
    bytes_: int,
    protocol: int = 6,
    src_country_code: str | None = None,
    dst_country_code: str | None = None,
) -> dict[str, Any]:
    """Build a flow record with the fields the writer maps to tags/fields."""
    flow: dict[str, Any] = {
        "src_ip": src_ip,
        "dst_ip": dst_ip,
        "src_port": 1234,
        "dst_port": 80,
        "protocol": protocol,
        "tos": 0,
        "tcp_flags": 0x1B,
        "bytes": bytes_,
        "packets": max(1, bytes_ // 500),
        "unix_secs": unix_secs,
    }
    if src_country_code:
        flow["src_country_code"] = src_country_code
    if dst_country_code:
        flow["dst_country_code"] = dst_country_code
    return flow


async def write_and_wait(instance: InfluxDBStorage, flows: list[dict[str, Any]], count: int):
    """Write flows, flush the batch queue, and wait until queryable.

    The batched write API posts asynchronously; poll until the bucket
    exposes the expected number of flows records (or time out).
    """
    written = await instance.write_flows(flows)
    assert written == len(flows)
    await instance.flush()

    start, stop = flows[0]["unix_secs"] - 1, flows[-1]["unix_secs"] + 1

    async def count_rows() -> int:
        rows = await instance.query_flows(
            _rfc3339(start), _rfc3339(stop), filters=None, limit=10000
        )
        return len(rows)

    for _ in range(30):
        if await count_rows() >= count:
            return
        await asyncio.sleep(0.5)
    raise AssertionError(f"flows did not become queryable within 15s (wrote {count})")


def _rfc3339(unix_secs: int) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(unix_secs, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


# Each test gets its own minute in January 2020 to stay isolated.
T0 = 1577836800  # 2020-01-01T00:00:00Z


async def test_write_and_query_flows_round_trip(storage):
    """Written flows must be queryable with filters, one row per flow.

    Rows must be pivoted: fields as columns (bytes, packets) with tags
    preserved - not one record per field.
    """
    flows = [
        make_flow(T0, "10.0.0.1", "10.0.0.9", 1000),
        make_flow(T0 + 1, "10.0.0.2", "10.0.0.9", 2000),
        make_flow(T0 + 2, "10.0.0.1", "10.0.0.9", 3000),
    ]
    await write_and_wait(storage, flows, count=3)

    result = await storage.query_flows(_rfc3339(T0 - 1), _rfc3339(T0 + 60))
    assert len(result) == 3

    # Pivoted row shape: fields and tags as columns, no Flux internals
    first = result[0]
    assert first["src_ip"] == "10.0.0.1"
    assert first["bytes"] == 1000
    assert first["packets"] == 2
    assert "_field" not in first
    assert "_value" not in first

    filtered = await storage.query_flows(
        _rfc3339(T0 - 1), _rfc3339(T0 + 60), filters={"src_ip": "10.0.0.1"}
    )
    assert len(filtered) == 2

    # Limit applies after filtering
    limited = await storage.query_flows(
        _rfc3339(T0 - 1), _rfc3339(T0 + 60), filters={"src_ip": "10.0.0.1"}, limit=1
    )
    assert len(limited) == 1


async def test_top_talkers(storage):
    """Top talkers must aggregate bytes per source IP and sort."""
    flows = [
        make_flow(T0 + 60, "10.0.1.1", "10.0.1.9", 100),
        make_flow(T0 + 61, "10.0.1.1", "10.0.1.9", 150),
        make_flow(T0 + 62, "10.0.1.2", "10.0.1.9", 500),
    ]
    await write_and_wait(storage, flows, count=3)

    talkers = await storage.get_top_talkers(_rfc3339(T0 + 59), _rfc3339(T0 + 120), limit=10)
    assert len(talkers) == 2
    assert talkers[0]["src_ip"] == "10.0.1.1"
    assert talkers[0]["value"] == 250
    assert talkers[1]["value"] == 500


async def test_protocol_distribution(storage):
    """Protocol distribution must sum bytes per protocol tag."""
    flows = [
        make_flow(T0 + 120, "10.0.2.1", "10.0.2.9", 300, protocol=6),
        make_flow(T0 + 121, "10.0.2.2", "10.0.2.9", 100, protocol=6),
        make_flow(T0 + 122, "10.0.2.3", "10.0.2.9", 400, protocol=17),
    ]
    await write_and_wait(storage, flows, count=3)

    dist = await storage.get_protocol_distribution(_rfc3339(T0 + 119), _rfc3339(T0 + 180))
    by_proto = {str(row["protocol"]): row["bytes"] for row in dist}
    assert by_proto.get("6") == 400
    assert by_proto.get("17") == 400


async def test_geo_distribution(storage):
    """Geo distribution must aggregate sent/received/flows/unique IPs per country."""
    flows = [
        make_flow(T0 + 240, "1.1.1.1", "9.9.9.9", 100, src_country_code="US",
                  dst_country_code="DE"),
        make_flow(T0 + 241, "2.2.2.2", "8.8.8.8", 50, src_country_code="US",
                  dst_country_code="US"),
        make_flow(T0 + 242, "3.3.3.3", "7.7.7.7", 10, src_country_code="DE",
                  dst_country_code="US"),
    ]
    await write_and_wait(storage, flows, count=3)

    rows = await storage.get_geo_distribution(_rfc3339(T0 + 239), _rfc3339(T0 + 300))
    by_code = {row["country_code"]: row for row in rows}

    us = by_code["US"]
    assert us["bytes_sent"] == 150
    assert us["bytes_received"] == 60
    assert us["flows"] == 2
    assert us["unique_ips"] == 2

    de = by_code["DE"]
    assert de["bytes_sent"] == 10
    assert de["bytes_received"] == 100
    assert de["flows"] == 1

    # Sorted by total bytes: US (210) before DE (110)
    assert rows[0]["country_code"] == "US"


async def test_bandwidth_timeseries(storage):
    """Bandwidth aggregation must window the synthetic flows."""
    flows = [
        make_flow(T0 + 300, "10.0.4.1", "10.0.4.9", 100),
        make_flow(T0 + 301, "10.0.4.1", "10.0.4.9", 200),
    ]
    await write_and_wait(storage, flows, count=2)

    series = await storage.get_bandwidth_timeseries(
        _rfc3339(T0 + 299), _rfc3339(T0 + 360), interval="1m"
    )
    total = sum(point["bytes"] or 0 for point in series)
    assert total == 300
