"""FlowSight Processing Pipeline

Wires the collector's parsed flows through enrichment, storage,
detection, and alerting. Each stage is failure-isolated: a crash in
one stage is logged and never blocks the others, so ingestion stays
alive.
"""

from typing import Any

from flowsight import get_logger, settings
from flowsight.detection.statistical import StatisticalAnomalyDetector
from flowsight.storage.influxdb import InfluxDBStorage

logger = get_logger(__name__)


class Pipeline:
    """Processes parsed flow records through the full FlowSight stack.

    Stages, in order: enrichment (optional) -> storage (optional) ->
    statistical detection -> threshold alerting. Stages are enabled by
    injection and configuration; any stage can fail without taking
    down the others.
    """

    def __init__(
        self,
        storage: Any | None = None,
        alert_manager: Any | None = None,
        enrichment_manager: Any | None = None,
        detector: StatisticalAnomalyDetector | None = None,
    ):
        self.storage = storage
        self.alert_manager = alert_manager
        self.enrichment_manager = enrichment_manager
        self.detector = detector or self._default_detector()
        self.flows_processed = 0

    @staticmethod
    def _default_detector() -> StatisticalAnomalyDetector:
        return StatisticalAnomalyDetector(
            z_threshold=settings.detection.statistical.zscore_threshold,
            min_samples=settings.detection.statistical.min_samples,
        )

    @classmethod
    async def from_settings(cls) -> "Pipeline":
        """Build a pipeline from the global settings.

        Degrades gracefully: storage is None if InfluxDB is
        unreachable, and enrichment is skipped if disabled in config.
        The alert manager is the global singleton so alerts generated
        here are visible to the API.
        """
        from flowsight.alerting.manager import get_alert_manager
        from flowsight.enrichment.manager import get_enrichment_manager

        storage: InfluxDBStorage | None = InfluxDBStorage()
        try:
            await storage.connect()
        except Exception as e:
            logger.warning("pipeline_storage_unavailable", url=settings.storage.url, error=str(e))
            await storage.disconnect()
            storage = None

        alert_manager = await get_alert_manager()

        enrichment_manager = None
        if settings.enrichment.enabled:
            enrichment_manager = await get_enrichment_manager()

        return cls(
            storage=storage,
            alert_manager=alert_manager,
            enrichment_manager=enrichment_manager,
        )

    async def stop(self) -> None:
        """Release pipeline resources."""
        if self.enrichment_manager is not None:
            try:
                await self.enrichment_manager.close()
            except Exception as e:
                logger.warning("pipeline_enrichment_close_failed", error=str(e))
        if self.storage is not None:
            try:
                await self.storage.disconnect()
            except Exception as e:
                logger.warning("pipeline_storage_close_failed", error=str(e))

    async def process_flows(self, flows: list[dict[str, Any]]) -> None:
        """Run a batch of parsed flows through the pipeline."""
        if not flows:
            return

        flows = await self._enrich(flows)
        await self._store(flows)
        await self._detect(flows)
        await self._alert(flows)

        self.flows_processed += len(flows)
        logger.debug("pipeline_batch_complete", flow_count=len(flows))

    async def _enrich(self, flows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Enrich flows; on failure, continue with the originals."""
        if self.enrichment_manager is None:
            return flows
        try:
            return await self.enrichment_manager.enrich_batch_async(flows)
        except Exception as e:
            logger.exception("pipeline_enrichment_failed", error=str(e), flow_count=len(flows))
            return flows

    async def _store(self, flows: list[dict[str, Any]]) -> None:
        """Write flows to storage; on failure, keep processing."""
        if self.storage is None:
            return
        try:
            written = await self.storage.write_flows(flows)
            logger.debug("pipeline_flows_stored", count=written)
        except Exception as e:
            logger.exception("pipeline_storage_failed", error=str(e), flow_count=len(flows))

    async def _detect(self, flows: list[dict[str, Any]]) -> None:
        """Feed the statistical detector and surface anomalies."""
        if not settings.detection.statistical.enabled or self.detector is None:
            return
        try:
            await self.detector.add_batch(flows)
            results = await self.detector.detect_batch(flows)
            anomaly_count = sum(1 for batch in results for r in batch if r.is_anomaly)
            if anomaly_count:
                logger.warning(
                    "pipeline_anomalies_detected",
                    count=anomaly_count,
                    flow_count=len(flows),
                )
        except Exception as e:
            logger.exception("pipeline_detection_failed", error=str(e))

    async def _alert(self, flows: list[dict[str, Any]]) -> None:
        """Evaluate threshold rules and dispatch alerts."""
        if self.alert_manager is None:
            return
        try:
            alerts = await self.alert_manager.evaluate_batch(flows)
            if alerts:
                logger.info("pipeline_alerts_generated", count=len(alerts))
        except Exception as e:
            logger.exception("pipeline_alerting_failed", error=str(e))
