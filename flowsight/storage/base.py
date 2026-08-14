"""
Storage Backend Base Class

Abstract interface for flow data storage.
"""

from abc import ABC, abstractmethod
from typing import Any


class StorageBackend(ABC):
    """Abstract base class for storage backends."""
    
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to storage."""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to storage."""
        pass
    
    @abstractmethod
    async def write_flows(self, flows: list[dict[str, Any]]) -> int:
        """Write flow records to storage. Returns count written."""
        pass
    
    @abstractmethod
    async def query_flows(
        self,
        start: str,
        stop: str,
        filters: dict[str, Any] | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Query flow records from storage."""
        pass
    
    @abstractmethod
    async def get_top_talkers(
        self,
        start: str,
        stop: str,
        limit: int = 10,
        by: str = "bytes",
    ) -> list[dict[str, Any]]:
        """Get top talkers (source IPs by bytes/packets)."""
        pass
    
    @abstractmethod
    async def get_protocol_distribution(
        self,
        start: str,
        stop: str,
    ) -> list[dict[str, Any]]:
        """Get protocol distribution."""
        pass
    
    @abstractmethod
    async def get_bandwidth_timeseries(
        self,
        start: str,
        stop: str,
        interval: str = "1m",
    ) -> list[dict[str, Any]]:
        """Get bandwidth time series."""
        pass