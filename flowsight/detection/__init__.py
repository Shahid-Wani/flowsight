"""
FlowSight Detection Module

Anomaly detection engines: statistical (z-score) and ML (IsolationForest).
"""

from flowsight.detection.statistical import StatisticalAnomalyDetector, DetectionResult
from flowsight.detection.ml import MLAnomalyDetector

__all__ = [
    "StatisticalAnomalyDetector",
    "DetectionResult",
    "MLAnomalyDetector",
]