"""
Threshold-based Alert Engine

Evaluates flows against configured threshold rules and generates alerts.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from flowsight import get_logger
from flowsight.config import settings

logger = get_logger(__name__)


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class ThresholdRule:
    """Threshold-based alert rule."""
    name: str
    field: str
    operator: str  # >, <, >=, <=, ==, !=
    value: float
    severity: AlertSeverity = AlertSeverity.WARNING
    description: str = ""
    enabled: bool = True
    cooldown_seconds: int = 300  # Minimum time between alerts for same rule

    def evaluate(self, flow_value: float) -> bool:
        """Evaluate if the flow value triggers this rule."""
        if not self.enabled:
            return False

        ops = {
            ">": lambda x, y: x > y,
            "<": lambda x, y: x < y,
            ">=": lambda x, y: x >= y,
            "<=": lambda x, y: x <= y,
            "==": lambda x, y: x == y,
            "!=": lambda x, y: x != y,
        }

        if self.operator not in ops:
            logger.warning("invalid_operator", rule=self.name, operator=self.operator)
            return False

        return ops[self.operator](flow_value, self.value)


@dataclass
class Alert:
    """Generated alert."""
    rule_name: str
    severity: AlertSeverity
    message: str
    flow_data: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    acknowledged: bool = False
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None


class ThresholdAlertEngine:
    """Evaluates flows against threshold rules and generates alerts."""

    def __init__(self):
        self.rules: list[ThresholdRule] = []
        self._alert_handlers: list[Callable[[Alert], Any]] = []
        self._last_alert_time: dict[str, datetime] = {}
        self._alert_history: list[Alert] = []
        self._max_history = 10000

    def add_rule(self, rule: ThresholdRule):
        """Add a threshold rule."""
        self.rules.append(rule)
        logger.info("threshold_rule_added", rule=rule.name, field=rule.field, operator=rule.operator, value=rule.value)

    def remove_rule(self, rule_name: str):
        """Remove a threshold rule by name."""
        self.rules = [r for r in self.rules if r.name != rule_name]
        logger.info("threshold_rule_removed", rule=rule_name)

    def add_handler(self, handler: Callable[[Alert], Any]):
        """Add an alert handler (sync or async)."""
        self._alert_handlers.append(handler)

    def load_rules_from_config(self):
        """Load rules from configuration."""
        if not settings.detection.threshold.enabled:
            return

        for rule_config in settings.detection.threshold.rules:
            rule = ThresholdRule(
                name=rule_config.name,
                field=rule_config.field,
                operator=rule_config.operator,
                value=rule_config.value,
                severity=AlertSeverity(rule_config.severity),
                description=f"Threshold rule: {rule_config.field} {rule_config.operator} {rule_config.value}",
            )
            self.add_rule(rule)

    def evaluate_flow(self, flow: dict[str, Any]) -> list[Alert]:
        """Evaluate a single flow against all rules."""
        alerts = []

        for rule in self.rules:
            if not rule.enabled:
                continue

            flow_value = flow.get(rule.field)
            if flow_value is None:
                continue

            try:
                value = float(flow_value)
            except (ValueError, TypeError):
                continue

            if rule.evaluate(value):
                # Check cooldown
                now = datetime.utcnow()
                last_alert = self._last_alert_time.get(rule.name)
                if last_alert and (now - last_alert).total_seconds() < rule.cooldown_seconds:
                    continue

                # Generate alert
                alert = Alert(
                    rule_name=rule.name,
                    severity=rule.severity,
                    message=f"Threshold exceeded: {rule.field} {rule.operator} {rule.value} (value: {value})",
                    flow_data=flow,
                )

                alerts.append(alert)
                self._last_alert_time[rule.name] = now
                self._alert_history.append(alert)

                # Trim history
                if len(self._alert_history) > self._max_history:
                    self._alert_history = self._alert_history[-self._max_history:]

                logger.warning("alert_generated", rule=rule.name, severity=rule.severity.value, flow_value=value)

        return alerts

    async def evaluate_flow_async(self, flow: dict[str, Any]) -> list[Alert]:
        """Evaluate flow and dispatch alerts asynchronously."""
        alerts = self.evaluate_flow(flow)

        for alert in alerts:
            await self._dispatch_alert(alert)

        return alerts

    async def _dispatch_alert(self, alert: Alert):
        """Dispatch alert to all handlers."""
        for handler in self._alert_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(alert)
                else:
                    handler(alert)
            except Exception as e:
                logger.exception("alert_handler_failed", handler=handler.__name__, error=str(e))

    def get_alert_history(
        self,
        limit: int = 100,
        severity: AlertSeverity | None = None,
        rule_name: str | None = None,
        since: datetime | None = None,
    ) -> list[Alert]:
        """Get alert history with optional filters."""
        alerts = self._alert_history

        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        if rule_name:
            alerts = [a for a in alerts if a.rule_name == rule_name]
        if since:
            alerts = [a for a in alerts if a.timestamp >= since]

        return alerts[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Get alert engine statistics."""
        return {
            "total_rules": len(self.rules),
            "enabled_rules": len([r for r in self.rules if r.enabled]),
            "total_alerts": len(self._alert_history),
            "alerts_by_severity": {
                s.value: len([a for a in self._alert_history if a.severity == s])
                for s in AlertSeverity
            },
            "handlers": len(self._alert_handlers),
        }


# Default rules for quick setup
def create_default_rules() -> list[ThresholdRule]:
    """Create default threshold rules."""
    return [
        ThresholdRule(
            name="high_bandwidth",
            field="bytes",
            operator=">",
            value=100_000_000,  # 100 MB
            severity=AlertSeverity.WARNING,
            description="High bandwidth flow detected (>100MB)",
        ),
        ThresholdRule(
            name="very_high_bandwidth",
            field="bytes",
            operator=">",
            value=1_000_000_000,  # 1 GB
            severity=AlertSeverity.CRITICAL,
            description="Very high bandwidth flow detected (>1GB)",
        ),
        ThresholdRule(
            name="many_packets",
            field="packets",
            operator=">",
            value=100_000,
            severity=AlertSeverity.WARNING,
            description="High packet count flow detected (>100k packets)",
        ),
        ThresholdRule(
            name="long_duration",
            field="duration",
            operator=">",
            value=3600,  # 1 hour
            severity=AlertSeverity.INFO,
            description="Long duration flow detected (>1 hour)",
        ),
    ]