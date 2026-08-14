"""
FlowSight Alerting Module

Threshold-based alerting, alert history, and notification handlers.
"""

from flowsight.alerting.threshold import ThresholdAlertEngine, ThresholdRule, AlertSeverity
from flowsight.alerting.manager import AlertManager, AlertHandler
from flowsight.alerting.handlers import LogHandler, WebhookHandler, EmailHandler

__all__ = [
    "ThresholdAlertEngine",
    "ThresholdRule",
    "AlertSeverity",
    "AlertManager",
    "AlertHandler",
    "LogHandler",
    "WebhookHandler",
    "EmailHandler",
]