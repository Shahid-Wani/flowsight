"""Tests for top-talker enrichment and alert persistence helpers.

The fold/merge helpers are pure and run without InfluxDB; the
persistence round-trip is covered by the integration suite.
"""

from datetime import datetime

from flowsight.alerting.threshold import Alert, AlertSeverity


class TestEnrichTalkers:
    def test_dominant_row_wins_per_talker(self):
        """The highest-bytes combination row provides the representative fields."""
        from flowsight.storage.influxdb import _enrich_talkers

        talkers = [{"src_ip": "10.0.0.1", "value": 444}, {"src_ip": "10.0.0.2", "value": 222}]
        dominant_rows = [
            # same IP, two combinations: the 333-byte row must win
            {
                "src_ip": "10.0.0.1",
                "dst_ip": "9.9.9.9",
                "protocol": "17",
                "src_country_code": "US",
                "src_asn": "65001",
                "src_asn_org": "Acme",
                "_value": 111,
            },
            {
                "src_ip": "10.0.0.1",
                "dst_ip": "8.8.8.8",
                "protocol": "6",
                "src_country_code": "DE",
                "src_asn": "65002",
                "src_asn_org": "Globex",
                "_value": 333,
            },
            {
                "src_ip": "10.0.0.2",
                "dst_ip": "7.7.7.7",
                "protocol": "6",
                "src_country_code": "US",
                "src_asn": "65001",
                "src_asn_org": "Acme",
                "_value": 222,
            },
        ]
        packets_by_ip = {"10.0.0.1": 40, "10.0.0.2": 5}

        enriched = _enrich_talkers(talkers, dominant_rows, packets_by_ip)

        first = enriched[0]
        assert first["dst_ip"] == "8.8.8.8"  # from the dominant (333-byte) row
        assert first["protocol"] == 6  # numeric for the frontend
        assert first["country_code"] == "DE"
        assert first["asn"] == 65002
        assert first["asn_org"] == "Globex"
        assert first["packets"] == 40

        second = enriched[1]
        assert second["protocol"] == 6
        assert second["asn_org"] == "Acme"
        assert second["packets"] == 5

    def test_missing_tags_leave_fields_unset(self):
        """Flows without enrichment produce null tag columns - no fields set."""
        from flowsight.storage.influxdb import _enrich_talkers

        talkers = [{"src_ip": "10.0.0.1", "value": 100}]
        dominant_rows = [
            {
                "src_ip": "10.0.0.1",
                "dst_ip": None,
                "protocol": None,
                "src_country_code": None,
                "src_asn": None,
                "src_asn_org": None,
                "_value": 100,
            }
        ]

        enriched = _enrich_talkers(talkers, dominant_rows, {})

        assert enriched[0]["src_ip"] == "10.0.0.1"
        assert "protocol" not in enriched[0]
        assert "country_code" not in enriched[0]
        assert "asn" not in enriched[0]
        assert "packets" not in enriched[0]

    def test_unknown_talker_and_bad_numbers_tolerated(self):
        """Rows for non-top IPs are ignored; non-numeric tags are skipped."""
        from flowsight.storage.influxdb import _enrich_talkers

        talkers = [{"src_ip": "10.0.0.1", "value": 100}]
        dominant_rows = [
            {
                "src_ip": "10.9.9.9",
                "dst_ip": "1.1.1.1",
                "protocol": "6",
                "src_country_code": "US",
                "src_asn": "65001",
                "src_asn_org": "Acme",
                "_value": 1,
            },
            {
                "src_ip": "10.0.0.1",
                "dst_ip": "2.2.2.2",
                "protocol": "not-a-number",
                "src_country_code": "US",
                "src_asn": "also-bad",
                "src_asn_org": "Acme",
                "_value": 100,
            },
        ]

        enriched = _enrich_talkers(talkers, dominant_rows, {})

        first = enriched[0]
        assert first["dst_ip"] == "2.2.2.2"
        assert "protocol" not in first  # non-numeric -> unset, not string
        assert "asn" not in first
        assert first["country_code"] == "US"
        assert first["asn_org"] == "Acme"


def make_alert(
    rule_name: str = "test_rule", severity: AlertSeverity = AlertSeverity.WARNING
) -> Alert:
    return Alert(
        rule_name=rule_name,
        severity=severity,
        message="Threshold exceeded",
        flow_data={"src_ip": "10.0.0.1", "bytes": 500},
    )


def alert_row(a: Alert) -> dict:
    """Shape read_alerts returns: string severity, iso timestamps."""
    return {
        "id": a.id,
        "rule_name": a.rule_name,
        "severity": a.severity.value,
        "message": a.message,
        "flow_data": a.flow_data,
        "timestamp": a.timestamp.isoformat(),
        "acknowledged": False,
        "acknowledged_by": None,
        "acknowledged_at": None,
    }


class TestAlertSerialization:
    def test_alert_to_point_builds(self):
        """The point must build from an alert."""
        from flowsight.storage.influxdb import alert_to_point

        alert = make_alert()
        point = alert_to_point(alert)
        assert point is not None

    def test_merge_alert_acks(self):
        """Ack rows must set acknowledged state on matching alerts by id."""
        from flowsight.storage.influxdb import merge_alert_acks

        a1 = make_alert("rule_one")
        a2 = make_alert("rule_two")
        ack_rows = [
            {"alert_id": a1.id, "acknowledged_by": "alice", "_time": datetime(2020, 1, 1, 12, 0, 0)}
        ]

        merged = merge_alert_acks([alert_row(a1), alert_row(a2)], ack_rows)

        by_id = {a["id"]: a for a in merged}
        assert by_id[a1.id]["acknowledged"] is True
        assert by_id[a1.id]["acknowledged_by"] == "alice"
        assert by_id[a1.id]["acknowledged_at"] == "2020-01-01T12:00:00"
        assert by_id[a2.id]["acknowledged"] is False
        assert by_id[a2.id]["acknowledged_by"] is None
