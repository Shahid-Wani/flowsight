"""Tests for real-time alert broadcasting and cooldown hydration.

The broadcast loop's new-alert filter and the cooldown hydration fold
are tested as pure functions; the WebSocket end-to-end path is covered
by the API integration suite.
"""

from datetime import datetime, timezone


class TestNewAlertFilter:
    def test_selects_only_alerts_strictly_after_last_seen(self):
        """Alerts at or before last_seen must not re-broadcast every tick."""
        from flowsight.api.websocket import _new_alerts_since

        rows = [
            {"id": "a", "timestamp": "2020-01-01T00:00:05+00:00"},
            {"id": "b", "timestamp": "2020-01-01T00:00:07+00:00"},
            {"id": "c", "timestamp": "2020-01-01T00:00:05+00:00"},  # == last_seen
            {"id": "d", "timestamp": "2020-01-01T00:00:01+00:00"},  # older
        ]

        new = _new_alerts_since(rows, "2020-01-01T00:00:05+00:00")

        assert [a["id"] for a in new] == ["b"]

    def test_empty_and_malformed_rows_tolerated(self):
        """Missing timestamps must not crash the loop."""
        from flowsight.api.websocket import _new_alerts_since

        assert _new_alerts_since([], "2020-01-01T00:00:05+00:00") == []
        new = _new_alerts_since([{"id": "x"}], "2020-01-01T00:00:05+00:00")
        assert new == []


class TestCooldownHydration:
    def test_latest_alert_time_per_rule(self):
        """The latest persisted alert per rule is the cooldown record."""
        from flowsight.storage.influxdb import _cooldowns_from_alert_rows

        rows = [
            {
                "rule_name": "high_bytes",
                "_time": datetime(2020, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            },
            {
                "rule_name": "high_bytes",
                "_time": datetime(2020, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
            },
            {
                "rule_name": "many_packets",
                "_time": datetime(2020, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
            },
        ]

        cooldowns = _cooldowns_from_alert_rows(rows)

        assert cooldowns["high_bytes"] == datetime(2020, 1, 1, 12, 5, 0, tzinfo=timezone.utc)
        assert cooldowns["many_packets"] == datetime(2020, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
        assert len(cooldowns) == 2

    def test_malformed_rows_tolerated(self):
        """Missing rule/time rows are skipped."""
        from flowsight.storage.influxdb import _cooldowns_from_alert_rows

        assert _cooldowns_from_alert_rows([]) == {}
        assert (
            _cooldowns_from_alert_rows([{"rule_name": "x"}, {"_time": datetime(2020, 1, 1)}]) == {}
        )
