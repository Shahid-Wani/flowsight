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

        # Tags (indexed)
        for tag_field in [
            "src_ip",
            "dst_ip",
            "protocol",
            "src_port",
            "dst_port",
            "tos",
            "tcp_flags",
        ]:
            if tag_field in flow and flow[tag_field] is not None:
                point.tag(tag_field, str(flow[tag_field]))

        # Fields (values)
        for field_name, value in flow.items():
            if field_name in [
                "src_ip",
                "dst_ip",
                "protocol",
                "src_port",
                "dst_port",
                "tos",
                "tcp_flags",
            ]:
                continue  # Already added as tags
            if field_name in ["unix_secs", "unix_nsecs", "sys_uptime", "flow_sequence"]:
                continue  # Metadata
            if isinstance(value, (int, float, bool)):
                point.field(field_name, value)

        return point

    async def query_flows(
        self, start: str, stop: str, filters: dict[str, Any] | None = None, limit: int = 1000
    ) -> list[dict[str, Any]]:
        """Query flow records from InfluxDB."""
        if not self._connected:
            await self.connect()

        flux_query = f"""
        from(bucket: "{settings.storage.bucket}")
          |> range(start: {start}, stop: {stop})
          |> filter(fn: (r) => r._measurement == "flow")
          |> limit(n: {limit})
        """

        if filters:
            for key, value in filters.items():
                flux_query += f'  |> filter(fn: (r) => r.{key} == "{value}")\n'

        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, self._query_flux, flux_query)
            return result
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

        field = "byte_count" if by == "bytes" else "packet_count"

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
          |> filter(fn: (r) => r._field == "byte_count")
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
          |> filter(fn: (r) => r._field == "byte_count")
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
