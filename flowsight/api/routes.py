"""
FlowSight API Routes

REST API endpoints for flow data queries.
"""

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from flowsight.api.main import storage
from flowsight import get_logger

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