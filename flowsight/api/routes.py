"""
FlowSight API Routes

REST API endpoints for flow data queries and alerting.
"""

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from flowsight import get_logger
from flowsight.api.main import storage
from flowsight.alerting.manager import get_alert_manager
from flowsight.alerting.threshold import Alert, AlertSeverity

logger = get_logger(__name__)

router = APIRouter()


# Request/Response Models
class TimeRange(BaseModel):
    start: str = Field(default_factory=lambda: (datetime.utcnow() - timedelta(hours=1)).isoformat())
    stop: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class FlowQueryRequest(TimeRange):
    filters: dict[str, Any] | None = None
    limit: int = Field(default=1000, ge=1, le=10000)


class TopTalkersRequest(TimeRange):
    limit: int = Field(default=10, ge=1, le=100)
    by: str = Field(default="bytes", pattern="^(bytes|packets)$")


class BandwidthRequest(TimeRange):
    interval: str = Field(default="1m", pattern="^(10s|30s|1m|5m|15m|1h)$")


class FlowResponse(BaseModel):
    flows: list[dict[str, Any]]
    count: int


class TopTalkersResponse(BaseModel):
    talkers: list[dict[str, Any]]


class BandwidthResponse(BaseModel):
    series: list[dict[str, Any]]


class ProtocolDistributionResponse(BaseModel):
    distribution: list[dict[str, Any]]


# Alert models
class AlertResponse(BaseModel):
    id: str
    rule_name: str
    severity: AlertSeverity
    message: str
    flow_data: dict[str, Any]
    timestamp: str
    acknowledged: bool
    acknowledged_by: str | None = None
    acknowledged_at: str | None = None


class AlertsResponse(BaseModel):
    alerts: list[AlertResponse]
    total: int


class AlertSummaryResponse(BaseModel):
    total: int
    critical: int
    warning: int
    info: int


class AcknowledgeResponse(BaseModel):
    success: bool
    message: str


# Dependency to get storage
async def get_storage():
    if storage is None:
        raise HTTPException(status_code=503, detail="Storage not initialized")
    return storage


@router.get("/flows", response_model=FlowResponse)
async def query_flows(
    start: str = Query(..., description="Start time (RFC3339 or relative like -1h)"),
    stop: str = Query(..., description="Stop time (RFC3339 or now)"),
    src_ip: str | None = Query(None, description="Filter by source IP"),
    dst_ip: str | None = Query(None, description="Filter by destination IP"),
    protocol: str | None = Query(None, description="Filter by protocol"),
    limit: int = Query(1000, ge=1, le=10000),
    storage_backend=Depends(get_storage),
):
    """Query flow records with optional filters."""
    try:
        filters = {}
        if src_ip:
            filters["src_ip"] = src_ip
        if dst_ip:
            filters["dst_ip"] = dst_ip
        if protocol:
            filters["protocol"] = protocol

        flows = await storage_backend.query_flows(start, stop, filters, limit)
        return FlowResponse(flows=flows, count=len(flows))
    except Exception as e:
        logger.exception("query_flows_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/top-talkers", response_model=TopTalkersResponse)
async def get_top_talkers(
    start: str = Query(..., description="Start time"),
    stop: str = Query(..., description="Stop time"),
    limit: int = Query(10, ge=1, le=100),
    by: str = Query("bytes", pattern="^(bytes|packets)$"),
    storage_backend=Depends(get_storage),
):
    """Get top talkers by bytes or packets."""
    try:
        talkers = await storage_backend.get_top_talkers(start, stop, limit, by)
        return TopTalkersResponse(talkers=talkers)
    except Exception as e:
        logger.exception("top_talkers_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bandwidth", response_model=BandwidthResponse)
async def get_bandwidth(
    start: str = Query(..., description="Start time"),
    stop: str = Query(..., description="Stop time"),
    interval: str = Query("1m", pattern="^(10s|30s|1m|5m|15m|1h)$"),
    storage_backend=Depends(get_storage),
):
    """Get bandwidth time series."""
    try:
        series = await storage_backend.get_bandwidth_timeseries(start, stop, interval)
        return BandwidthResponse(series=series)
    except Exception as e:
        logger.exception("bandwidth_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/protocols", response_model=ProtocolDistributionResponse)
async def get_protocol_distribution(
    start: str = Query(..., description="Start time"),
    stop: str = Query(..., description="Stop time"),
    storage_backend=Depends(get_storage),
):
    """Get protocol distribution."""
    try:
        distribution = await storage_backend.get_protocol_distribution(start, stop)
        return ProtocolDistributionResponse(distribution=distribution)
    except Exception as e:
        logger.exception("protocol_distribution_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/geo-map")
async def get_geo_map(
    start: str = Query(..., description="Start time"),
    stop: str = Query(..., description="Stop time"),
    storage_backend=Depends(get_storage),
):
    """Get geographic distribution of traffic."""
    try:
        # For now, return mock data structure
        # In production, this would query InfluxDB for geo data
        return {
            "locations": [
                {
                    "country_code": "US",
                    "country_name": "United States",
                    "latitude": 37.0902,
                    "longitude": -95.7129,
                    "bytes_sent": 1073741824,
                    "bytes_received": 536870912,
                    "flows": 15000,
                    "unique_ips": 500
                },
                {
                    "country_code": "CN",
                    "country_name": "China",
                    "latitude": 35.8617,
                    "longitude": 104.1954,
                    "bytes_sent": 536870912,
                    "bytes_received": 268435456,
                    "flows": 8000,
                    "unique_ips": 200
                },
                {
                    "country_code": "DE",
                    "country_name": "Germany",
                    "latitude": 51.1657,
                    "longitude": 10.4515,
                    "bytes_sent": 268435456,
                    "bytes_received": 134217728,
                    "flows": 5000,
                    "unique_ips": 150
                }
            ]
        }
    except Exception as e:
        logger.exception("geo_map_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/summary")
async def get_summary(
    start: str = Query(..., description="Start time"),
    stop: str = Query(..., description="Stop time"),
    storage_backend=Depends(get_storage),
):
    """Get summary statistics for a time range."""
    try:
        # Get multiple stats in parallel
        import asyncio

        bandwidth_task = storage_backend.get_bandwidth_timeseries(start, stop, "1m")
        talkers_task = storage_backend.get_top_talkers(start, stop, 5, "bytes")
        protocols_task = storage_backend.get_protocol_distribution(start, stop)

        bandwidth, talkers, protocols = await asyncio.gather(
            bandwidth_task, talkers_task, protocols_task
        )

        total_bytes = sum(point.get("bytes", 0) for point in bandwidth)
        total_flows = len(bandwidth)  # Approximation

        return {
            "time_range": {"start": start, "stop": stop},
            "total_bytes": total_bytes,
            "total_flows_estimate": total_flows,
            "top_talkers": talkers,
            "protocol_distribution": protocols,
            "bandwidth_series": bandwidth,
        }
    except Exception as e:
        logger.exception("summary_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# Alert endpoints
@router.get("/alerts", response_model=AlertsResponse)
async def get_alerts(
    start: str = Query(..., description="Start time"),
    stop: str = Query(..., description="Stop time"),
    limit: int = Query(100, ge=1, le=1000),
    severity: AlertSeverity | None = Query(None, description="Filter by severity"),
    acknowledged: bool | None = Query(None, description="Filter by acknowledged status"),
):
    """Get alerts with optional filters."""
    try:
        manager = await get_alert_manager()
        all_alerts = manager.get_alert_history(limit=limit)
        
        # Apply filters
        filtered = all_alerts
        if severity:
            filtered = [a for a in filtered if a.severity == severity]
        if acknowledged is not None:
            filtered = [a for a in filtered if a.acknowledged == acknowledged]
        
        alert_responses = [
            AlertResponse(
                id=str(i),
                rule_name=a.rule_name,
                severity=a.severity,
                message=a.message,
                flow_data=a.flow_data,
                timestamp=a.timestamp.isoformat(),
                acknowledged=a.acknowledged,
                acknowledged_by=a.acknowledged_by,
                acknowledged_at=a.acknowledged_at.isoformat() if a.acknowledged_at else None,
            )
            for i, a in enumerate(filtered)
        ]
        
        return AlertsResponse(alerts=alert_responses, total=len(alert_responses))
    except Exception as e:
        logger.exception("get_alerts_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts/summary", response_model=AlertSummaryResponse)
async def get_alert_summary():
    """Get alert summary statistics."""
    try:
        manager = await get_alert_manager()
        stats = manager.get_stats()
        return AlertSummaryResponse(
            total=stats.get("total_alerts", 0),
            critical=stats.get("alerts_by_severity", {}).get("critical", 0),
            warning=stats.get("alerts_by_severity", {}).get("warning", 0),
            info=stats.get("alerts_by_severity", {}).get("info", 0),
        )
    except Exception as e:
        logger.exception("alert_summary_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alerts/{alert_id}/acknowledge", response_model=AcknowledgeResponse)
async def acknowledge_alert(alert_id: str, acknowledged_by: str = "api-user"):
    """Acknowledge an alert."""
    try:
        manager = await get_alert_manager()
        # Convert alert_id to index
        try:
            idx = int(alert_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid alert ID")
        
        success = manager.acknowledge_alert(idx, acknowledged_by)
        if not success:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        return AcknowledgeResponse(success=True, message="Alert acknowledged")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("acknowledge_alert_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))