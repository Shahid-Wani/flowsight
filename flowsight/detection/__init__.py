"""
FlowSight Detection Module

Anomaly detection engines: statistical (z-score) and ML (IsolationForest).
"""

from flowsight.detection.ml import MLAnomalyDetector
from flowsight.detection.statistical import DetectionResult, StatisticalAnomalyDetector

__all__ = [
    "StatisticalAnomalyDetector",
    "DetectionResult",
    "MLAnomalyDetector",
]
