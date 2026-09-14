"""Smoke tests for critical package behavior.

These tests guard the bugs fixed on Day 1 of the repair effort:
API importability, YAML config loading, CLI entry points, and the
NetFlow v5 collector handler.
"""

import struct
from ipaddress import IPv4Address

from fastapi.testclient import TestClient


def test_api_module_imports():
    """The API package must import without circular-import errors."""
    from flowsight.api.main import app

    assert app is not None


def test_api_health_endpoint():
    """GET /health must return 200 and a healthy payload."""
    from flowsight.api.main import app

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_api_starts_degraded_without_influxdb():
    """The API must still start when InfluxDB is unreachable.

    Runs the app lifespan (via TestClient context manager) with no
    InfluxDB available: /health must respond and storage-backed
    endpoints must return 503 instead of crashing the server.
    """
    from flowsight.api.main import app

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200

        flows = client.get("/api/v1/flows", params={"start": "-5m", "stop": "now"})
        assert flows.status_code == 503


def test_config_loads_yaml():
    """Settings(_yaml_file=...) must populate fields from the YAML file."""
    from flowsight.config import Settings

    settings = Settings(_yaml_file="config.example.yaml")
    assert settings.storage.token == "your-influxdb-token"
    assert settings.api.port == 8000
    rule_names = [r.name for r in settings.detection.threshold.rules]
    assert "high_bandwidth" in rule_names
    assert "many_connections" in rule_names


def test_load_config_function():
    """load_config(path) must return settings populated from that file."""
    from flowsight.config import load_config

    loaded = load_config("config.example.yaml")
    assert loaded.storage.token == "your-influxdb-token"
    assert [r.name for r in loaded.detection.threshold.rules] == [
        "high_bandwidth",
        "many_connections",
    ]


def test_env_vars_use_double_underscore_form(monkeypatch):
    """Nested settings must be overridable via SECTION__FIELD env vars.

    docker-compose.yaml relies on this form (STORAGE__URL, API__JWT_SECRET,
    ...) - flat forms like STORAGE_URL are silently ignored by
    pydantic-settings env_nested_delimiter.
    """
    from flowsight.config import Settings

    monkeypatch.setenv("STORAGE__TOKEN", "env-token-123")
    monkeypatch.setenv("API__JWT_SECRET", "env-secret-456")

    fresh = Settings()
    assert fresh.storage.token == "env-token-123"
    assert fresh.api.jwt_secret == "env-secret-456"


def test_enrichment_cli_entrypoint():
    """flowsight-enrich console script target must exist."""
    from flowsight.enrichment.cli import main

    assert callable(main)


def test_detection_cli_entrypoint():
    """flowsight-detect console script target must exist."""
    from flowsight.detection.cli import main

    assert callable(main)


def test_alert_handlers_registered_from_config():
    """get_alert_manager() must register handlers from settings.alerting."""
    import flowsight.alerting.manager as am
    from flowsight import settings

    am._alert_manager = None  # reset the global singleton

    original = settings.alerting.handlers
    try:
        settings.alerting.handlers = [
            type(original[0])(type="log", level="info"),
            type(original[0])(type="webhook", url="http://example.com/hook", headers={}, template="", level="info"),
        ]
        import asyncio

        manager = asyncio.run(am.get_alert_manager())
        names = [h.name for h in manager.handlers]
        assert "log" in names
        assert "webhook" in names
    finally:
        settings.alerting.handlers = original
        am._alert_manager = None


def _build_netflow_v5_packet() -> bytes:
    """Build a minimal valid NetFlow v5 packet with one flow record."""
    header = struct.pack(
        "!HHIIIIBBH",
        5,  # version
        1,  # flow count
        1000,  # sys uptime (ms)
        1725950000,  # unix secs
        0,  # unix nsecs
        42,  # flow sequence
        0,  # engine type
        0,  # engine id
        0,  # sampling interval
    )
    record = struct.pack(
        "!IIIHHIIIIHHBBBBHHBBH",
        int(IPv4Address("192.168.1.100")),  # src addr
        int(IPv4Address("10.0.0.1")),  # dst addr
        int(IPv4Address("0.0.0.0")),  # next hop
        1,  # input iface
        2,  # output iface
        100,  # packets
        50000,  # bytes
        100,  # start time
        200,  # end time
        1234,  # src port
        80,  # dst port
        0,  # pad1
        0x1B,  # tcp flags
        6,  # protocol (TCP)
        0,  # tos
        65001,  # src as
        65002,  # dst as
        24,  # src mask
        24,  # dst mask
        0,  # pad2
    )
    return header + record


class TestNetFlowV5Handler:
    def test_parses_valid_packet(self):
        """The collector v5 handler must parse a valid v5 packet."""
        from flowsight.collector.server import NetFlowV5Handler

        packet = _build_netflow_v5_packet()
        handler = NetFlowV5Handler()

        assert handler.can_handle(packet)
        flows = handler.parse(packet, "127.0.0.1", 9999)

        assert len(flows) == 1
        assert flows[0]["src_ip"] == "192.168.1.100"
        assert flows[0]["dst_ip"] == "10.0.0.1"
        assert flows[0]["bytes"] == 50000
        assert flows[0]["packets"] == 100
        assert flows[0]["protocol"] == 6
        assert flows[0]["source_ip"] == "127.0.0.1"

    def test_rejects_short_packet(self):
        """The collector v5 handler must reject truncated packets."""
        from flowsight.collector.server import NetFlowV5Handler

        handler = NetFlowV5Handler()
        assert not handler.can_handle(b"\x00\x05\x00\x01")
        assert handler.parse(b"\x00\x05", "127.0.0.1", 9999) == []

    def test_rejects_wrong_version(self):
        """The collector v5 handler must ignore non-v5 packets."""
        from flowsight.collector.server import NetFlowV5Handler

        packet = struct.pack("!HH", 9, 1)
        handler = NetFlowV5Handler()
        assert not handler.can_handle(packet)
