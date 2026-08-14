"""
Statistical Anomaly Detection

Z-score based anomaly detection for network flow data.
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from flowsight import get_logger
from flowsight.config import settings

logger = get_logger(__name__)


@dataclass
class DetectionResult:
    """Result of anomaly detection."""
    is_anomaly: bool
    score: float
    threshold: float
    field: str
    value: float
    mean: float
    std: float
    z_score: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


class StatisticalAnomalyDetector:
    """Statistical anomaly detection using z-score."""

    def __init__(
        self,
        window_size: int = 1000,
        z_threshold: float = 3.0,
        min_samples: int = 30,
        fields: list[str] | None = None,
    ):
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.min_samples = min_samples
        self.fields = fields or ["bytes", "packets", "duration", "src_port", "dst_port"]
        
        # Rolling windows per field: {field: [values]}
        self._windows: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
        
        # Statistics cache
        self._stats_cache: dict[str, tuple[float, float]] = {}  # (mean, std)
        self._cache_dirty = True

    async def add_sample(self, flow: dict[str, Any]):
        """Add a flow sample to the rolling windows."""
        async with self._lock:
            for field in self.fields:
                value = flow.get(field)
                if value is not None:
                    try:
                        val = float(value)
                        self._windows[field].append(val)
                        # Trim window
                        if len(self._windows[field]) > self.window_size:
                            self._windows[field] = self._windows[field][-self.window_size:]
                    except (ValueError, TypeError):
                        pass
            self._cache_dirty = True

    async def add_batch(self, flows: list[dict[str, Any]]):
        """Add multiple flows efficiently."""
        async with self._lock:
            for flow in flows:
                for field in self.fields:
                    value = flow.get(field)
                    if value is not None:
                        try:
                            val = float(value)
                            self._windows[field].append(val)
                            if len(self._windows[field]) > self.window_size:
                                self._windows[field] = self._windows[field][-self.window_size:]
                        except (ValueError, TypeError):
                            pass
            self._cache_dirty = True

    def _compute_stats(self, field: str) -> tuple[float, float] | None:
        """Compute mean and std for a field."""
        values = self._windows.get(field, [])
        if len(values) < self.min_samples:
            return None
        
        arr = np.array(values)
        mean = float(np.mean(arr))
        std = float(np.std(arr))
        
        if std == 0:
            return None
        
        return (mean, std)

    def _update_cache(self):
        """Update statistics cache."""
        self._stats_cache = {}
        for field in self.fields:
            stats = self._compute_stats(field)
            if stats:
                self._stats_cache[field] = stats
        self._cache_dirty = False

    async def detect(self, flow: dict[str, Any]) -> list[DetectionResult]:
        """Detect anomalies in a single flow."""
        async with self._lock:
            if self._cache_dirty:
                self._update_cache()

            results = []
            for field in self.fields:
                value = flow.get(field)
                if value is None:
                    continue
                
                try:
                    val = float(value)
                except (ValueError, TypeError):
                    continue

                stats = self._stats_cache.get(field)
                if not stats:
                    continue

                mean, std = stats
                if std == 0:
                    continue

                z_score = abs((val - mean) / std)
                is_anomaly = z_score > self.z_threshold

                result = DetectionResult(
                    is_anomaly=is_anomaly,
                    score=z_score,
                    threshold=self.z_threshold,
                    field=field,
                    value=val,
                    mean=mean,
                    std=std,
                    z_score=z_score,
                    metadata={
                        "window_size": len(self._windows[field]),
                        "rule": f"zscore_{field}",
                    },
                )
                results.append(result)

                if is_anomaly:
                    logger.warning(
                        "statistical_anomaly_detected",
                        field=field,
                        value=val,
                        mean=mean,
                        std=std,
                        z_score=z_score,
                        threshold=self.z_threshold,
                    )

                # Add this sample to window for next detection
                self._windows[field].append(val)
                if len(self._windows[field]) > self.window_size:
                    self._windows[field] = self._windows[field][-self.window_size:]
                self._cache_dirty = True

            return results

    async def detect_batch(self, flows: list[dict[str, Any]]) -> list[list[DetectionResult]]:
        """Detect anomalies in a batch of flows."""
        async with self._lock:
            if self._cache_dirty:
                self._update_cache()

            all_results = []
            for flow in flows:
                results = []
                for field in self.fields:
                    value = flow.get(field)
                    if value is None:
                        continue
                    
                    try:
                        val = float(value)
                    except (ValueError, TypeError):
                        continue

                    stats = self._stats_cache.get(field)
                    if not stats:
                        continue

                    mean, std = stats
                    if std == 0:
                        continue

                    z_score = abs((val - mean) / std)
                    is_anomaly = z_score > self.z_threshold

                    result = DetectionResult(
                        is_anomaly=is_anomaly,
                        score=z_score,
                        threshold=self.z_threshold,
                        field=field,
                        value=val,
                        mean=mean,
                        std=std,
                        z_score=z_score,
                        metadata={
                            "window_size": len(self._windows[field]),
                            "rule": f"zscore_{field}",
                        },
                    )
                    results.append(result)

                    # Update window for next detection
                    self._windows[field].append(val)
                    if len(self._windows[field]) > self.window_size:
                        self._windows[field] = self._windows[field][-self.window_size:]
                
                if results:
                    self._cache_dirty = True
                
                all_results.append(results)

            return all_results

    def get_stats(self) -> dict[str, Any]:
        """Get detector statistics."""
        return {
            "window_size": self.window_size,
            "z_threshold": self.z_threshold,
            "min_samples": self.min_samples,
            "fields": self.fields,
            "samples_per_field": {
                field: len(values) for field, values in self._windows.items()
            },
            "cached_stats": {
                field: {"mean": stats[0], "std": stats[1]} 
                for field, stats in self._stats_cache.items()
            },
        }

    def reset(self):
        """Reset all windows and cache."""
        self._windows.clear()
        self._stats_cache.clear()
        self._cache_dirty = True


def create_default_detector() -> StatisticalAnomalyDetector:
    """Create detector with default configuration from settings."""
    if not settings.detection.statistical.enabled:
        return None
    
    return StatisticalAnomalyDetector(
        window_size=settings.detection.statistical.min_samples * 10,
        z_threshold=settings.detection.statistical.zscore_threshold,
        min_samples=settings.detection.statistical.min_samples,
    )