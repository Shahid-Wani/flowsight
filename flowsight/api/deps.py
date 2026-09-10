"""Shared runtime dependencies for the FlowSight API.

This module exists to break the import cycle between
``flowsight.api.main``, ``flowsight.api.routes`` and
``flowsight.api.websocket``. The storage instance is bound here at
startup (in the app lifespan) and consumed lazily by the routers.
"""

from fastapi import HTTPException

from flowsight.storage.influxdb import InfluxDBStorage

storage: InfluxDBStorage | None = None


async def get_storage() -> InfluxDBStorage:
    """Return the shared storage instance.

    Raises:
        HTTPException: 503 if the storage backend is not initialized yet.
    """
    if storage is None:
        raise HTTPException(status_code=503, detail="Storage not initialized")
    return storage
