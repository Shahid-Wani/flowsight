"""Tests for Flux time-range validation and protocol name mapping."""

import pytest
from fastapi.testclient import TestClient


class TestTimeRangeValidation:
    @pytest.mark.parametrize(
        "value",
        [
            # Flux keywords
            "now",
            "now()",
            # integer epoch seconds (valid in Flux range())
            "1577836800",
            # relative durations, simple and compound
            "-5m",
            "-1h",
            "-30s",
            "-7d",
            "-2w",
            "1h",
            "-1h30m",
            "-2h15m",
            "-1d12h",
            "-1h30m45s",
            # RFC3339 with explicit offset
            "2020-01-01T00:00:00Z",
            "2020-01-01T00:00:00.123456Z",
            "2020-01-01T00:00:00.123456789Z",
            "2020-01-01T01:00:00+02:00",
        ],
    )
    def test_accepts_flux_time_literals(self, value):
        """Everything Flux's range() accepts must pass validation."""
        from flowsight.storage.influxdb import validate_time_range

        validate_time_range(value, "now")
        validate_time_range("-1h", value)

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            " ",
            "1 hour",
            "yesterday",
            "now; drop(bucket)",
            '2020-01-01" |> yield(name:"x',
            "-1x",
            "+1h",
            None,
            # Parses as a datetime in Python, but is NOT a Flux time literal:
            "2020-01-01",
            "2020-01-01 00:00:00",
            "2020-01-01T00:00:00",
            "2020-01-01T00:00:00z",
        ],
    )
    def test_rejects_non_flux_literals(self, bad):
        """Anything Flux would reject must 400 instead of reaching a query."""
        from flowsight.storage.influxdb import validate_time_range

        with pytest.raises(ValueError, match="invalid time"):
            validate_time_range(bad, "now")
        with pytest.raises(ValueError, match="invalid time"):
            validate_time_range("now", bad)

    async def test_query_rejects_before_connecting(self):
        """Validation must run before any connection attempt."""
        from flowsight.storage.influxdb import InfluxDBStorage

        storage = InfluxDBStorage()  # never connected
        with pytest.raises(ValueError, match="invalid time"):
            await storage.query_flows("not-a-time", "now")

    def test_route_returns_400_for_invalid_time(self):
        """The API must answer 400 (not 500) for garbage time ranges."""
        from flowsight.api import deps
        from flowsight.api.main import app
        from flowsight.storage.influxdb import InfluxDBStorage

        deps.storage = InfluxDBStorage()  # validation fires before connect
        try:
            client = TestClient(app)
            response = client.get("/api/v1/flows", params={"start": "garbage", "stop": "now"})
            assert response.status_code == 400
        finally:
            deps.storage = None


class FakeProtocolStorage:
    def __init__(self, rows):
        self.rows = rows

    async def get_protocol_distribution(self, start: str, stop: str):
        return self.rows


class TestProtocolMapping:
    def test_protocol_name_known_numbers(self):
        from flowsight.api.protocols import protocol_name

        assert protocol_name("6") == "TCP"
        assert protocol_name(17) == "UDP"
        assert protocol_name(1) == "ICMP"
        assert protocol_name(58) == "ICMPv6"

    def test_protocol_name_unknown_number(self):
        from flowsight.api.protocols import protocol_name

        assert protocol_name(99) == "Proto 99"

    def test_protocol_name_non_numeric(self):
        from flowsight.api.protocols import protocol_name

        assert protocol_name("TCP") == "TCP"
        assert protocol_name(None) == "Unknown"

    def test_route_maps_numbers_to_names(self):
        from flowsight.api import deps
        from flowsight.api.main import app

        deps.storage = FakeProtocolStorage(
            [
                {"protocol": "6", "bytes": 100},
                {"protocol": "17", "bytes": 50},
                {"protocol": "99", "bytes": 1},
            ]
        )
        try:
            client = TestClient(app)
            response = client.get("/api/v1/protocols", params={"start": "-1h", "stop": "now"})
            assert response.status_code == 200
            names = [row["protocol"] for row in response.json()["distribution"]]
            assert names == ["TCP", "UDP", "Proto 99"]
        finally:
            deps.storage = None
