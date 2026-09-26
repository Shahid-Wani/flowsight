"""Tests for the ML detector production wiring.

The train-then-detect round trip and the alert conversion run locally
(sklearn, no InfluxDB); the pipeline test verifies the wiring with the
config gate.
"""

import asyncio

from flowsight.alerting.threshold import AlertSeverity
from flowsight.detection.ml import MLAnomalyDetector

# The detector requires every feature field to be present
FEATURE_FIELDS = {
    "bytes": 100,
    "packets": 2,
    "duration": 50,
    "src_port": 1234,
    "dst_port": 80,
    "protocol": 6,
}


def make_flow_like(count: int = 12, **overrides) -> list[dict]:
    """Uniform 'normal' flows for training/detection."""
    flows = []
    for i in range(count):
        flow = dict(FEATURE_FIELDS)
        flow["bytes"] = 100 + i
        flow["duration"] = 50 + i
        flow.update(overrides)
        flows.append(flow)
    return flows


def train_sync(detector: MLAnomalyDetector, flows: list[dict]) -> bool:
    return asyncio.run(detector.train(flows))


class TestTrainThenDetect:
    def test_train_returns_true_and_saves_model(self, tmp_path):
        """train() must fit and persist the model."""
        detector = MLAnomalyDetector(model_path=str(tmp_path / "model.pkl"))

        assert train_sync(detector, make_flow_like()) is True
        assert (tmp_path / "model.pkl").exists()

    def test_detect_after_training_returns_results(self, tmp_path):
        """detect_batch must return real results once trained."""
        detector = MLAnomalyDetector(model_path=str(tmp_path / "model.pkl"))
        train_sync(detector, make_flow_like())

        results = asyncio.run(detector.detect_batch(make_flow_like(count=5)))
        assert all(r is not None for r in results)
        assert all(not r.is_anomaly for r in results)  # normal flows look normal

    def test_detect_flags_wildly_different_flow(self, tmp_path):
        """A flow far outside the training distribution must flag."""
        detector = MLAnomalyDetector(model_path=str(tmp_path / "model.pkl"))
        train_sync(detector, make_flow_like())

        wild = dict(FEATURE_FIELDS, bytes=10**9, packets=10**6)
        results = asyncio.run(detector.detect_batch([wild]))

        assert results[0] is not None
        assert results[0].is_anomaly is True

    def test_untrained_returns_none(self, tmp_path):
        """Untrained detector returns None results (existing behavior)."""
        detector = MLAnomalyDetector(model_path=str(tmp_path / "model.pkl"))

        results = asyncio.run(detector.detect_batch(make_flow_like(count=5)))
        assert all(r is None for r in results)

    def test_model_reload_round_trip(self, tmp_path):
        """A saved model must load into a new detector and detect."""
        first = MLAnomalyDetector(model_path=str(tmp_path / "model.pkl"))
        train_sync(first, make_flow_like())

        second = MLAnomalyDetector(model_path=str(tmp_path / "model.pkl"))
        results = asyncio.run(second.detect_batch(make_flow_like(count=5)))
        assert all(r is not None for r in results)


class TestMLAnomalyAlerts:
    def test_ml_result_to_alert_fields(self, tmp_path):
        """An ML anomaly must become a persisted, dispatchable alert."""
        from flowsight.detection.ml import ml_result_to_alert

        detector = MLAnomalyDetector(model_path=str(tmp_path / "model.pkl"))
        train_sync(detector, make_flow_like())
        wild = dict(FEATURE_FIELDS, bytes=10**9, packets=10**6)
        result = asyncio.run(detector.detect_batch([wild]))[0]

        alert = ml_result_to_alert(result)

        assert alert.rule_name == "ml_anomaly"
        assert alert.severity == AlertSeverity.WARNING
        assert alert.flow_data["bytes"] == 10**9
        assert alert.message  # non-empty message

    def test_ml_severity_from_config(self, tmp_path, monkeypatch):
        """The configured ml_severity must flow into the alert."""
        from flowsight import settings
        from flowsight.detection.ml import ml_result_to_alert

        monkeypatch.setattr(settings.detection.ml, "ml_severity", "critical")

        detector = MLAnomalyDetector(model_path=str(tmp_path / "model.pkl"))
        train_sync(detector, make_flow_like())
        wild = dict(FEATURE_FIELDS, bytes=10**9, packets=10**6)
        result = asyncio.run(detector.detect_batch([wild]))[0]

        alert = ml_result_to_alert(result)
        assert alert.severity == AlertSeverity.CRITICAL


class TestConfigGate:
    def test_ml_disabled_by_default(self):
        """The ML detector must be gated by settings.detection.ml.enabled."""
        from flowsight import settings
        from flowsight.detection.ml import create_default_ml_detector

        assert settings.detection.ml.enabled is False
        assert create_default_ml_detector() is None

    def test_ml_severity_config_default(self):
        """MLDetectionConfig must expose the ml alert severity knob."""
        from flowsight.config import MLDetectionConfig

        config = MLDetectionConfig()
        assert config.ml_severity == "warning"

    def test_ml_enabled_creates_detector(self, tmp_path, monkeypatch):
        """With the gate on, create_default_ml_detector must return one."""
        from flowsight import settings
        from flowsight.detection.ml import create_default_ml_detector

        monkeypatch.setattr(settings.detection.ml, "enabled", True)
        monkeypatch.setattr(settings.detection.ml, "model_path", str(tmp_path / "m.pkl"))

        detector = create_default_ml_detector()
        assert detector is not None
