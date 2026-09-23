"""
InfluxDB Storage Backend

Time-series storage for flow data using InfluxDB v2 API.
"""

import asyncio
import json
import re
from datetime import datetime
from typing import Any

from influxdb_client import InfluxDBClient, Point, WriteOptions

from flowsight import get_logger, settings
from flowsight.alerting.threshold import Alert
from flowsight.storage.base import StorageBackend

logger = get_logger(__name__)

# Flux time literal forms accepted by range(). Keep these aligned with
# what Flux itself parses; anything accepted here must not make Flux
# error, and anything Flux rejects must be refused before querying.
_NOW_RE = re.compile(r"^now(?:\(\))?$")
_EPOCH_RE = re.compile(r"^\d+$")
_DURATION_RE = re.compile(r"^-?(\d+(ns|us|ms|s|m|h|d|w|mo|y))+$")
_RFC3339_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")


def normalize_time_range(start: str | None, stop: str | None) -> tuple[str, str]:
    """Validate client time values and return Flux-safe literals.

    Accepts the forms ``range()`` supports: ``now`` / ``now()``, integer
    epoch seconds, relative durations (simple or compound: ``-1h30m``),
    and RFC3339 timestamps with an explicit ``Z`` or numeric offset.

    Bare ``now`` is normalized to ``now()``: in Flux, bare ``now`` is
    the *function* ``() => time``, not a time value - passing it to
    ``range()`` fails with "value is not a time". Clients (including
    the dashboard) send ``stop=now``, so the friendly form is accepted
    and rewritten.

    Raises ValueError for anything else, so garbage or injected
    fragments never reach a Flux query. Validates form, not ordering.
    """
    normalized: list[str] = []
    for value in (start, stop):
        if not value:
            raise ValueError(f"invalid time value: {value!r}")
        if _NOW_RE.match(value):
            normalized.append("now()")
            continue
        if _EPOCH_RE.match(value) or _DURATION_RE.match(value) or _RFC3339_RE.match(value):
            normalized.append(value)
            continue
        raise ValueError(f"invalid time value: {value!r}")
    return normalized[0], normalized[1]


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
            "src_asn_org",
            "dst_asn_org",
        ]
        for tag_field in tag_fields:
            if flow.get(tag_field) is not None:
                point.tag(tag_field, str(flow[tag_field]))

        # Field values become point fields
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
        start, stop = normalize_time_range(start, stop)
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
        """Get top talkers by bytes or packets.

        Each talker is enriched with: packets total (both fields are
        summed regardless of the ``by`` ranking field), and the
        representative destination/protocol/country/ASN from the
        talker's dominant (highest-bytes) flow combination - the tags
        the dashboard's Top Talkers columns display.
        """
        start, stop = normalize_time_range(start, stop)
        if not self._connected:
            await self.connect()

        field = by

        sums_query = f"""
        from(bucket: "{settings.storage.bucket}")
          |> range(start: {start}, stop: {stop})
          |> filter(fn: (r) => r._measurement == "flow")
          |> filter(fn: (r) => r._field == "{field}")
          |> group(columns: ["src_ip"])
          |> sum()
          |> sort(columns: ["_value"], desc: true)
          |> limit(n: {limit})
        """
        packets_query = f"""
        from(bucket: "{settings.storage.bucket}")
          |> range(start: {start}, stop: {stop})
          |> filter(fn: (r) => r._measurement == "flow")
          |> filter(fn: (r) => r._field == "packets")
          |> group(columns: ["src_ip"])
          |> sum()
        """
        # Per flow combination: the dominant row per talker provides the
        # representative tags (main destination, protocol, country, ASN).
        dominant_query = f"""
        from(bucket: "{settings.storage.bucket}")
          |> range(start: {start}, stop: {stop})
          |> filter(fn: (r) => r._measurement == "flow")
          |> filter(fn: (r) => r._field == "bytes")
          |> group(columns: ["src_ip", "dst_ip", "protocol", "src_country_code", "src_asn", "src_asn_org"])
          |> sum()
        """

        try:
            loop = asyncio.get_running_loop()
            sums_rows, packets_rows, dominant_rows = await asyncio.gather(
                loop.run_in_executor(None, self._query_flux, sums_query),
                loop.run_in_executor(None, self._query_flux, packets_query),
                loop.run_in_executor(None, self._query_flux, dominant_query),
            )
        except Exception as e:
            logger.exception("top_talkers_query_failed", error=str(e))
            raise

        talkers = [{"src_ip": r.get("src_ip"), "value": r.get("_value")} for r in sums_rows]
        packets_by_ip = {r.get("src_ip"): r.get("_value") for r in packets_rows}
        return _enrich_talkers(talkers, dominant_rows, packets_by_ip)

    async def get_protocol_distribution(self, start: str, stop: str) -> list[dict[str, Any]]:
        """Get protocol distribution."""
        start, stop = normalize_time_range(start, stop)
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
        start, stop = normalize_time_range(start, stop)
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
        start, stop = normalize_time_range(start, stop)
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

    async def read_alert_cooldowns(self) -> dict[str, datetime]:
        """Read the last-fired time per rule from persisted alerts.

        Used to hydrate cooldown state on startup: without it, a
        restarted collector would re-fire alerts for conditions that
        already alerted before the restart.
        """
        if not self._connected:
            await self.connect()

        query = f"""
        from(bucket: "{settings.storage.bucket}")
          |> range(start: -7d, stop: now())
          |> filter(fn: (r) => r._measurement == "alert")
          |> group(columns: ["rule_name"])
          |> last()
        """

        try:
            loop = asyncio.get_running_loop()
            rows = await loop.run_in_executor(None, self._query_flux, query)
        except Exception as e:
            logger.exception("read_alert_cooldowns_failed", error=str(e))
            raise
        return _cooldowns_from_alert_rows(rows)

    async def write_alert(self, alert: Alert) -> None:
        """Persist an alert (measurement ``alert``).

        Cross-process visibility: the collector's pipeline and the API
        run in separate processes, so in-memory alert history is not
        shared - persistence is what makes collector-generated alerts
        visible to the API. Also survives restarts.
        """
        if not self._connected:
            await self.connect()

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._write_points, [alert_to_point(alert)])
            logger.debug("alert_persisted", alert_id=alert.id, rule=alert.rule_name)
        except Exception as e:
            logger.exception("alert_write_failed", alert_id=alert.id, error=str(e))
            raise

    async def write_alert_ack(self, alert_id: str, acknowledged_by: str) -> None:
        """Persist an alert acknowledgement (measurement ``alert_ack``).

        Point overwrite per alert id makes acks idempotent; the latest
        ack record wins when reading.
        """
        if not self._connected:
            await self.connect()

        point = (
            Point("alert_ack").tag("alert_id", alert_id).field("acknowledged_by", acknowledged_by)
        )
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._write_points, [point])
            logger.debug("alert_ack_persisted", alert_id=alert_id, by=acknowledged_by)
        except Exception as e:
            logger.exception("alert_ack_write_failed", alert_id=alert_id, error=str(e))
            raise

    async def read_alerts(
        self, start: str, stop: str, limit: int = 100, severity: str | None = None
    ) -> list[dict[str, Any]]:
        """Read persisted alerts with their ack state merged.

        Returns dicts shaped like the API's AlertResponse: id,
        rule_name, severity, message, flow_data (parsed from
        ``flow_json``), timestamp, acknowledged, acknowledged_by,
        acknowledged_at.
        """
        start, stop = normalize_time_range(start, stop)
        if not self._connected:
            await self.connect()

        severity_filter = ""
        if severity:
            severity_filter = f'  |> filter(fn: (r) => r.severity == "{severity}")\n'

        alerts_query = f"""
        from(bucket: "{settings.storage.bucket}")
          |> range(start: {start}, stop: {stop})
          |> filter(fn: (r) => r._measurement == "alert")
        {severity_filter}  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
          |> group()
          |> sort(columns: ["_time"], desc: true)
          |> limit(n: {limit})
        """
        acks_query = f"""
        from(bucket: "{settings.storage.bucket}")
          |> range(start: {start}, stop: {stop})
          |> filter(fn: (r) => r._measurement == "alert_ack")
          |> group(columns: ["alert_id"])
          |> last()
        """

        try:
            loop = asyncio.get_running_loop()
            alert_rows, ack_rows = await asyncio.gather(
                loop.run_in_executor(None, self._query_flux, alerts_query),
                loop.run_in_executor(None, self._query_flux, acks_query),
            )
        except Exception as e:
            logger.exception("read_alerts_query_failed", error=str(e))
            raise

        alerts = []
        for row in alert_rows:
            flow_data: dict[str, Any] = {}
            try:
                flow_data = json.loads(row.get("flow_json") or "{}")
            except (TypeError, ValueError):
                logger.warning("alert_flow_json_unparseable", alert_id=row.get("id"))
            alerts.append(
                {
                    "id": row.get("id"),
                    "rule_name": row.get("rule_name"),
                    "severity": row.get("severity"),
                    "message": row.get("message"),
                    "flow_data": flow_data,
                    "timestamp": row.get("_time").isoformat()
                    if hasattr(row.get("_time"), "isoformat")
                    else row.get("_time"),
                    "acknowledged": bool(row.get("acknowledged")),
                    "acknowledged_by": None,
                    "acknowledged_at": None,
                }
            )
        return merge_alert_acks(alerts, ack_rows)


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


def _to_int(value: Any) -> int | None:
    """Convert a tag value to int; None when missing or non-numeric."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _enrich_talkers(
    talkers: list[dict[str, Any]],
    dominant_rows: list[dict[str, Any]],
    packets_by_ip: dict[str | None, Any],
) -> list[dict[str, Any]]:
    """Enrich top talkers with representative fields from their flows.

    The dominant (highest-bytes) flow combination per talker provides
    the destination, protocol, country, and ASN the dashboard displays.
    Tag values (protocol, ASN) arrive as strings from InfluxDB and are
    converted to numbers for the frontend; missing or non-numeric tags
    leave the field unset.
    """
    dominant_by_ip: dict[str | None, dict[str, Any]] = {}
    for row in dominant_rows:
        ip = row.get("src_ip")
        current = dominant_by_ip.get(ip)
        if current is None or (row.get("_value") or 0) > (current.get("_value") or 0):
            dominant_by_ip[ip] = row

    enriched = []
    for talker in talkers:
        row = dict(talker)
        dominant = dominant_by_ip.get(talker.get("src_ip"))
        if dominant is not None:
            if dominant.get("dst_ip"):
                row["dst_ip"] = dominant["dst_ip"]
            protocol = _to_int(dominant.get("protocol"))
            if protocol is not None:
                row["protocol"] = protocol
            if dominant.get("src_country_code"):
                row["country_code"] = dominant["src_country_code"]
            asn = _to_int(dominant.get("src_asn"))
            if asn is not None:
                row["asn"] = asn
            if dominant.get("src_asn_org"):
                row["asn_org"] = dominant["src_asn_org"]
        packets = packets_by_ip.get(talker.get("src_ip"))
        if packets is not None:
            row["packets"] = int(packets)
        enriched.append(row)
    return enriched


def _cooldowns_from_alert_rows(rows: list[dict[str, Any]]) -> dict[str, datetime]:
    """Fold alert rows into per-rule last-alert times.

    The persisted alerts ARE the cooldown record (the pipeline writes
    every generated alert): the latest alert timestamp per rule is the
    moment that rule last fired.
    """
    cooldowns: dict[str, datetime] = {}
    for row in rows:
        rule = row.get("rule_name")
        alert_time = row.get("_time")
        if not rule or not hasattr(alert_time, "tzinfo"):
            continue
        current = cooldowns.get(rule)
        if current is None or alert_time > current:
            cooldowns[rule] = alert_time
    return cooldowns


def alert_to_point(alert: Alert) -> Point:
    """Serialize an alert to an InfluxDB point (measurement ``alert``).

    Tags: rule_name, severity. Fields: id, message, flow_json,
    acknowledged. Timestamped at generation time.
    """
    return (
        Point("alert")
        .time(alert.timestamp)
        .tag("rule_name", alert.rule_name)
        .tag("severity", alert.severity.value)
        .field("id", alert.id)
        .field("message", alert.message)
        .field("flow_json", json.dumps(alert.flow_data))
        .field("acknowledged", alert.acknowledged)
    )


def merge_alert_acks(
    alerts: list[dict[str, Any]], ack_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge ack records into alert rows by alert id.

    Sets ``acknowledged``/``acknowledged_by``/``acknowledged_at`` from
    the latest ack record per alert. Ack rows come from Flux in the
    default dialect: the acked-by user is in ``_value`` (the field
    value), not under the field's name.
    """
    acks_by_id: dict[str | None, dict[str, Any]] = {}
    for row in ack_rows:
        alert_id = row.get("alert_id")
        current = acks_by_id.get(alert_id)
        if current is None or (row.get("_time") or datetime.min) > (
            current.get("_time") or datetime.min
        ):
            acks_by_id[alert_id] = row

    merged = []
    for alert in alerts:
        row = dict(alert)
        ack = acks_by_id.get(alert.get("id"))
        if ack is not None:
            row["acknowledged"] = True
            row["acknowledged_by"] = ack.get("_value")
            ack_time = ack.get("_time")
            row["acknowledged_at"] = (
                ack_time.isoformat() if hasattr(ack_time, "isoformat") else ack_time
            )
        merged.append(row)
    return merged


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
        countries.values(), key=lambda c: c["bytes_sent"] + c["bytes_received"], reverse=True
    )
