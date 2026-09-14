"""
InfluxDB Storage Backend

Time-series storage for flow data using InfluxDB v2 API.
"""

import asyncio
from datetime import datetime
from typing import Any

from influxdb_client import InfluxDBClient, Point, WriteOptions

from flowsight import get_logger, settings
from flowsight.storage.base import StorageBackend

logger = get_logger(__name__)


class InfluxDBStorage(StorageBackend):
    """InfluxDB storage backend for flow data."""

    def __init__(self):
        self.client: InfluxDBClient | None = None
        self.write_api = None
        self.query_api = None
        self._connected = False

    async def connect(self) -> None:
        """Connect to InfluxDB."""
        if self._connected:
            return

        try:
            self.client = InfluxDBClient(
                url=settings.storage.url, token=settings.storage.token, org=settings.storage.org
            )

            self.write_api = self.client.write_api(
                write_options=WriteOptions(
                    batch_size=settings.storage.batch_size,
                    flush_interval=settings.storage.flush_interval * 1000,
                    retry_interval=5000,
                )
            )

            self.query_api = self.client.query_api()
            self._connected = True

            # Test connection
            buckets = self.client.buckets_api().find_buckets()
            logger.info("influxdb_connected", buckets_count=len(buckets.buckets))

        except Exception as e:
            logger.exception("influxdb_connection_failed", error=str(e))
            raise

    async def disconnect(self) -> None:
        """Disconnect from InfluxDB."""
        if self.write_api:
            self.write_api.close()
        if self.client:
            self.client.close()
        self._connected = False
        logger.info("influxdb_disconnected")

    async def write_flows(self, flows: list[dict[str, Any]]) -> int:
        """Write flow records to InfluxDB."""
        if not self._connected:
            await self.connect()

        if not flows:
            return 0

        points = []
        for flow in flows:
            try:
                point = self._flow_to_point(flow)
                points.append(point)
            except Exception as e:
                logger.warning("flow_to_point_failed", error=str(e), flow=flow)

        if not points:
            return 0

        try:
            # Write in a thread pool since influxdb-client is sync
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._write_points, points)
            logger.debug("flows_written", count=len(points))
            return len(points)
        except Exception as e:
            logger.exception("influxdb_write_failed", error=str(e))
            raise

    def _write_points(self, points: list[Point]):
        """Write points synchronously."""
        self.write_api.write(
            bucket=settings.storage.bucket, org=settings.storage.org, record=points
        )

    def _flow_to_point(self, flow: dict[str, Any]) -> Point:
        """Convert flow dict to InfluxDB Point."""
        # Use unix_secs as timestamp if available
        timestamp = flow.get("unix_secs")
        if timestamp:
            dt = datetime.fromtimestamp(timestamp)
        else:
            dt = datetime.utcnow()

        point = Point("flow").time(dt)

        # Tags (indexed): wire fields plus enrichment output we want to
        # filter queries on (GeoIP country, ASN).
        tag_fields = [
            "src_ip",
            "dst_ip",
            "protocol",
            "src_port",
            "dst_port",
            "tos",
            "tcp_flags",
            "src_country_code",
            "dst_country_code",
            "src_asn",
            "dst_asn",
        ]
        for tag_field in tag_fields:
            if flow.get(tag_field) is not None:
                point.tag(tag_field, str(flow[tag_field]))

        # Fields (values)
        for field_name, value in flow.items():
            if field_name in tag_fields:
                continue  # Already added as tags
            if field_name in ["unix_secs", "unix_nsecs", "sys_uptime", "flow_sequence"]:
                continue  # Metadata
            if isinstance(value, (int, float, bool)):
                point.field(field_name, value)

        return point

    async def query_flows(
        self, start: str, stop: str, filters: dict[str, Any] | None = None, limit: int = 1000
    ) -> list[dict[str, Any]]:
        """Query flow records from InfluxDB.

        Returns one row per flow record: tags preserved as columns and
        fields pivoted into columns (bytes, packets, ...). Filters are
        applied before the limit so filtered queries are correct.
        """
        if not self._connected:
            await self.connect()

        filter_lines = ""
        for key, value in (filters or {}).items():
            escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
            filter_lines += f'  |> filter(fn: (r) => r.{key} == "{escaped}")\n'

        flux_query = f"""
        from(bucket: "{settings.storage.bucket}")
          |> range(start: {start}, stop: {stop})
          |> filter(fn: (r) => r._measurement == "flow")
        {filter_lines}  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
          |> group()
          |> sort(columns: ["_time"], desc: false)
          |> limit(n: {limit})
        """

        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, self._query_flux, flux_query)
            return [_clean_flow_row(row) for row in result]
        except Exception as e:
            logger.exception("influxdb_query_failed", error=str(e))
            raise

    def _query_flux(self, query: str) -> list[dict[str, Any]]:
        """Execute Flux query synchronously."""
        tables = self.query_api.query(query, org=settings.storage.org)
        results = []
        for table in tables:
            for record in table.records:
                results.append(record.values)
        return results

    async def get_top_talkers(
        self, start: str, stop: str, limit: int = 10, by: str = "bytes"
    ) -> list[dict[str, Any]]:
        """Get top talkers by bytes or packets."""
        if not self._connected:
            await self.connect()

        field = by

        flux_query = f"""
        from(bucket: "{settings.storage.bucket}")
          |> range(start: {start}, stop: {stop})
          |> filter(fn: (r) => r._measurement == "flow")
          |> filter(fn: (r) => r._field == "{field}")
          |> group(columns: ["src_ip"])
          |> sum()
          |> sort(columns: ["_value"], desc: true)
          |> limit(n: {limit})
        """

        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, self._query_flux, flux_query)
            return [{"src_ip": r.get("src_ip"), "value": r.get("_value")} for r in result]
        except Exception as e:
            logger.exception("top_talkers_query_failed", error=str(e))
            raise

    async def get_protocol_distribution(self, start: str, stop: str) -> list[dict[str, Any]]:
        """Get protocol distribution."""
        if not self._connected:
            await self.connect()

        flux_query = f"""
        from(bucket: "{settings.storage.bucket}")
          |> range(start: {start}, stop: {stop})
          |> filter(fn: (r) => r._measurement == "flow")
          |> filter(fn: (r) => r._field == "bytes")
          |> group(columns: ["protocol"])
          |> sum()
          |> sort(columns: ["_value"], desc: true)
        """

        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, self._query_flux, flux_query)
            return [{"protocol": r.get("protocol"), "bytes": r.get("_value")} for r in result]
        except Exception as e:
            logger.exception("protocol_distribution_query_failed", error=str(e))
            raise

    async def get_bandwidth_timeseries(
        self, start: str, stop: str, interval: str = "1m"
    ) -> list[dict[str, Any]]:
        """Get bandwidth time series."""
        if not self._connected:
            await self.connect()

        flux_query = f"""
        from(bucket: "{settings.storage.bucket}")
          |> range(start: {start}, stop: {stop})
          |> filter(fn: (r) => r._measurement == "flow")
          |> filter(fn: (r) => r._field == "bytes")
          |> aggregateWindow(every: {interval}, fn: sum, createEmpty: true)
          |> yield(name: "bandwidth")
        """

        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, self._query_flux, flux_query)
            return [{"time": r.get("_time"), "bytes": r.get("_value")} for r in result]
        except Exception as e:
            logger.exception("bandwidth_timeseries_query_failed", error=str(e))
            raise

    async def get_geo_distribution(self, start: str, stop: str) -> list[dict[str, Any]]:
        """Get traffic distribution by source/destination country.

        Uses the ``src_country_code`` / ``dst_country_code`` tags written
        by the enrichment pipeline.
        """
        if not self._connected:
            await self.connect()

        bucket = settings.storage.bucket
        base_filter = 'r._measurement == "flow" and r._field == "bytes"'

        # Per (country, source ip) sums: bytes + unique IP counts
        sent_ip_query = f"""
        from(bucket: "{bucket}")
          |> range(start: {start}, stop: {stop})
          |> filter(fn: (r) => {base_filter} and exists r.src_country_code)
          |> group(columns: ["src_country_code", "src_ip"])
          |> sum()
        """
        # Flow record counts per source country
        flows_query = f"""
        from(bucket: "{bucket}")
          |> range(start: {start}, stop: {stop})
          |> filter(fn: (r) => {base_filter} and exists r.src_country_code)
          |> group(columns: ["src_country_code"])
          |> count()
        """
        # Bytes received, per destination country
        received_query = f"""
        from(bucket: "{bucket}")
          |> range(start: {start}, stop: {stop})
          |> filter(fn: (r) => {base_filter} and exists r.dst_country_code)
          |> group(columns: ["dst_country_code"])
          |> sum()
        """

        try:
            loop = asyncio.get_running_loop()
            sent_rows, flow_rows, recv_rows = await asyncio.gather(
                loop.run_in_executor(None, self._query_flux, sent_ip_query),
                loop.run_in_executor(None, self._query_flux, flows_query),
                loop.run_in_executor(None, self._query_flux, received_query),
            )
        except Exception as e:
            logger.exception("geo_distribution_query_failed", error=str(e))
            raise

        sent = _aggregate_geo_sent(sent_rows)
        flow_counts = {r.get("src_country_code"): r.get("_value") or 0 for r in flow_rows}
        for row in sent:
            row["flows"] = int(flow_counts.get(row["country_code"], 0))

        received = [
            {"country_code": r.get("dst_country_code"), "bytes": r.get("_value") or 0}
            for r in recv_rows
        ]
        return _merge_geo_rows(sent, received)

    async def flush(self) -> None:
        """Flush pending batched writes (used by integration tests)."""
        if self.write_api:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.write_api.flush)


def _clean_flow_row(row: dict[str, Any]) -> dict[str, Any]:
    """Drop Flux-internal columns from a pivoted flow row.

    Keeps tags and pivoted field columns; renames ``_time`` to ``time``.
    """
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        if key in ("result", "table"):
            continue
        if key.startswith("_") and key != "_time":
            continue
        cleaned["time" if key == "_time" else key] = value
    return cleaned


def _aggregate_geo_sent(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fold per-(country, ip) sum rows into per-country bytes + unique IPs."""
    per_country: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = row.get("src_country_code")
        if not code:
            continue
        entry = per_country.setdefault(code, {"bytes": 0.0, "unique_ips": 0, "_ips": set()})
        entry["bytes"] += row.get("_value") or 0
        entry["_ips"].add(row.get("src_ip"))

    return [
        {"country_code": code, "bytes": entry["bytes"], "unique_ips": len(entry["_ips"])}
        for code, entry in per_country.items()
    ]


def _merge_geo_rows(
    sent: list[dict[str, Any]], received: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge per-country sent and received aggregates, sorted by total bytes."""
    countries: dict[str, dict[str, Any]] = {}

    for row in sent:
        code = row.get("country_code")
        if not code:
            continue
        countries[code] = {
            "country_code": code,
            "bytes_sent": row.get("bytes", 0),
            "bytes_received": 0,
            "flows": row.get("flows", 0),
            "unique_ips": row.get("unique_ips", 0),
        }

    for row in received:
        code = row.get("country_code")
        if not code:
            continue
        entry = countries.setdefault(
            code,
            {
                "country_code": code,
                "bytes_sent": 0,
                "bytes_received": 0,
                "flows": 0,
                "unique_ips": 0,
            },
        )
        entry["bytes_received"] += row.get("bytes", 0)

    return sorted(
        countries.values(),
        key=lambda c: c["bytes_sent"] + c["bytes_received"],
        reverse=True,
    )
