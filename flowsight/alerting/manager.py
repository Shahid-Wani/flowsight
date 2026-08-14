"""
Alert Manager

Central manager for alerting - coordinates threshold engine, handlers, and alert history.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from flowsight import get_logger
from flowsight.alerting.threshold import ThresholdAlertEngine, ThresholdRule, Alert, AlertSeverity

logger = get_logger(__name__)


@dataclass
class AlertHandler:
    """Base alert handler interface."""
    name: str
    severity_filter: list[AlertSeverity] | None = None  # None = all severities

    def should_handle(self, alert: Alert) -> bool:
        """Check if this handler should process the alert."""
        if self.severity_filter is None:
            return True
        return alert.severity in self.severity_filter

    async def handle(self, alert: Alert):
        """Handle an alert (override in subclasses)."""
        raise NotImplementedError


class AlertManager:
    """Central alert management - coordinates engine, handlers, and persistence."""

    def __init__(self):
        self.engine = ThresholdAlertEngine()
        self.handlers: list[AlertHandler] = []
        self._running = False
        self._evaluation_task: asyncio.Task | None = None

    def add_handler(self, handler: AlertHandler):
        """Add an alert handler."""
        self.handlers.append(handler)
        self.engine.add_handler(self._handler_wrapper(handler))
        logger.info("alert_handler_added", handler=handler.name)

    def _handler_wrapper(self, handler: AlertHandler) -> Callable[[Alert], Any]:
        """Create a wrapper that checks severity filter before calling handler."""
        async def wrapper(alert: Alert):
            if handler.should_handle(alert):
                try:
                    await handler.handle(alert)
                except Exception as e:
                    logger.exception("alert_handler_error", handler=handler.name, error=str(e))
        return wrapper

    def load_default_rules(self):
        """Load default threshold rules from config."""
        self.engine.load_rules_from_config()

        # Add default rules if no config rules
        if not self.engine.rules:
            from flowsight.alerting.threshold import create_default_rules
            for rule in create_default_rules():
                self.engine.add_rule(rule)

    def add_custom_rule(self, rule: ThresholdRule):
        """Add a custom threshold rule."""
        self.engine.add_rule(rule)

    async def evaluate_flow(self, flow: dict[str, Any]) -> list[Alert]:
        """Evaluate a flow and dispatch alerts."""
        return await self.engine.evaluate_flow_async(flow)

    async def evaluate_batch(self, flows: list[dict[str, Any]]) -> list[Alert]:
        """Evaluate a batch of flows."""
        all_alerts = []
        for flow in flows:
            alerts = await self.evaluate_flow(flow)
            all_alerts.extend(alerts)
        return all_alerts

    def get_alert_history(
        self,
        limit: int = 100,
        severity: AlertSeverity | None = None,
        rule_name: str | None = None,
        since: datetime | None = None,
    ) -> list[Alert]:
        """Get alert history."""
        return self.engine.get_alert_history(limit, severity, rule_name, since)

    def acknowledge_alert(self, alert_index: int, acknowledged_by: str) -> bool:
        """Acknowledge an alert by history index."""
        alerts = self.engine._alert_history
        if 0 <= alert_index < len(alerts):
            alert = alerts[alert_index]
            alert.acknowledged = True
            alert.acknowledged_by = acknowledged_by
            alert.acknowledged_at = datetime.utcnow()
            logger.info("alert_acknowledged", index=alert_index, by=acknowledged_by)
            return True
        return False

    def get_stats(self) -> dict[str, Any]:
        """Get alert manager statistics."""
        return {
            **self.engine.get_stats(),
            "handlers": [
                {
                    "name": h.name,
                    "severity_filter": [s.value for s in h.severity_filter] if h.severity_filter else "all"
                }
                for h in self.handlers
            ],
        }


# Global alert manager instance
_alert_manager: AlertManager | None = None


async def get_alert_manager() -> AlertManager:
    """Get or create the global alert manager."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
        _alert_manager.load_default_rules()
    return _alert_manager


async def evaluate_flow_for_alerts(flow: dict[str, Any]) -> list[Alert]:
    """Convenience function to evaluate a flow for alerts."""
    manager = await get_alert_manager()
    return await manager.evaluate_flow(flow)