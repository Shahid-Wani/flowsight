"""Tests for the FlowSight processing pipeline.

The pipeline wires enrichment -> storage -> detection/alerting for
flows parsed by the collector. These tests verify the wiring with
fake backends: flows must reach storage, thresholds must fire alerts,
and a failure in any single stage must never kill the others.
"""

from typing import Any

from flowsight.alerting.manager import AlertManager
from flowsight.alerting.threshold import AlertSeverity, ThresholdRule


class FakeStorage:
    """In-memory storage backend recording write_flows calls."""

    def __init__(self, fail: bool = False):
        self.flows: list[dict[str, Any]] = []
        self.fail = fail
        self.closed = False

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        self.closed = True

    async def write_flows(self, flows: list[dict[str, Any]]) -> int:
        if self.fail:
            raise ConnectionError("storage unavailable")
        self.flows.extend(flows)
        return len(flows)


class FailingEnrichment:
    """Enrichment manager that always raises."""

    async def enrich_batch_async(self, flows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raise RuntimeError("enrichment exploded")


def make_alert_manager(rule_value: float = 1000) -> AlertManager:
    """AlertManager with a single high-bytes threshold rule."""
    manager = AlertManager()
    manager.add_custom_rule(
        ThresholdRule(
            name="test_high_bytes",
            field="bytes",
            operator=">",
            value=rule_value,
            severity=AlertSeverity.WARNING,
        )
    )
    return manager


def test_pipeline_module_exists():
    """The pipeline module must be importable."""
    from flowsight.pipeline import Pipeline

    assert Pipeline is not None


async def test_pipeline_writes_flows_to_storage():
    """Flows processed by the pipeline must land in storage."""
    from flowsight.pipeline import Pipeline

    storage = FakeStorage()
    pipeline = Pipeline(storage=storage, alert_manager=make_alert_manager())
    flows = [{"src_ip": "10.0.0.1", "dst_ip": "10.0.0.2", "bytes": 100, "packets": 2}]

    await pipeline.process_flows(flows)

    assert storage.flows == flows


async def test_pipeline_fires_threshold_alerts():
    """A flow exceeding a threshold rule must generate an alert."""
    from flowsight.pipeline import Pipeline

    storage = FakeStorage()
    manager = make_alert_manager(rule_value=1000)
    pipeline = Pipeline(storage=storage, alert_manager=manager)

    await pipeline.process_flows([{"src_ip": "10.0.0.1", "bytes": 50000, "packets": 100}])

    history = manager.get_alert_history(limit=10)
    assert len(history) == 1
    assert history[0].rule_name == "test_high_bytes"
    assert history[0].flow_data["bytes"] == 50000


async def test_pipeline_survives_storage_failure():
    """A storage outage must not prevent alerting."""
    from flowsight.pipeline import Pipeline

    storage = FakeStorage(fail=True)
    manager = make_alert_manager()
    pipeline = Pipeline(storage=storage, alert_manager=manager)

    await pipeline.process_flows([{"src_ip": "10.0.0.1", "bytes": 50000, "packets": 1}])

    assert len(manager.get_alert_history(limit=10)) == 1


async def test_pipeline_survives_enrichment_failure():
    """An enrichment crash must not prevent storage writes."""
    from flowsight.pipeline import Pipeline

    storage = FakeStorage()
    pipeline = Pipeline(
        storage=storage,
        alert_manager=make_alert_manager(),
        enrichment_manager=FailingEnrichment(),
    )
    flows = [{"src_ip": "10.0.0.1", "bytes": 100, "packets": 1}]

    await pipeline.process_flows(flows)

    assert storage.flows == flows


async def test_pipeline_works_without_storage():
    """Degraded mode: no storage configured, alerting still works."""
    from flowsight.pipeline import Pipeline

    manager = make_alert_manager()
    pipeline = Pipeline(storage=None, alert_manager=manager)

    await pipeline.process_flows([{"src_ip": "10.0.0.1", "bytes": 50000, "packets": 1}])

    assert len(manager.get_alert_history(limit=10)) == 1


async def test_pipeline_feeds_statistical_detector():
    """Processed flows must populate the statistical detector's windows."""
    from flowsight.pipeline import Pipeline

    storage = FakeStorage()
    pipeline = Pipeline(storage=storage, alert_manager=make_alert_manager())

    for i in range(5):
        await pipeline.process_flows([{"src_ip": "10.0.0.1", "bytes": 100 + i, "packets": i}])

    assert pipeline.detector is not None
    stats = pipeline.detector.get_stats()
    assert stats["samples_per_field"]["bytes"] == 5
