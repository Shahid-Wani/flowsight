"""
ML Anomaly Detection

Isolation Forest based anomaly detection for network flow data.
"""

import asyncio
import pickle
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from flowsight import get_logger
from flowsight.config import settings

logger = get_logger(__name__)


@dataclass
class MLDetectionResult:
    """Result of ML anomaly detection."""
    is_anomaly: bool
    score: float  # Anomaly score (negative = more anomalous)
    threshold: float
    features: dict[str, float]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


class MLAnomalyDetector:
    """Isolation Forest based anomaly detection."""

    def __init__(
        self,
        model_path: str | None = None,
        contamination: float = 0.01,
        n_estimators: int = 100,
        max_samples: str | int = "auto",
        random_state: int = 42,
        feature_fields: list[str] | None = None,
        retrain_interval: int = 10000,  # Retrain after this many samples
    ):
        self.model_path = Path(model_path) if model_path else Path(settings.detection.ml.model_path)
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.max_samples = max_samples
        self.random_state = random_state
        self.feature_fields = feature_fields or [
            "bytes", "packets", "duration", "src_port", "dst_port", "protocol"
        ]
        self.retrain_interval = retrain_interval

        # Model components
        self.model: IsolationForest | None = None
        self.scaler: StandardScaler | None = None
        
        # Training buffer
        self._training_buffer: list[np.ndarray] = []
        self._samples_since_retrain = 0
        
        # Load or initialize model
        self._load_or_init_model()

    def _load_or_init_model(self):
        """Load existing model or initialize new one."""
        if self.model_path.exists():
            try:
                data = joblib.load(self.model_path)
                self.model = data["model"]
                self.scaler = data["scaler"]
                self.feature_fields = data.get("feature_fields", self.feature_fields)
                logger.info("ml_model_loaded", path=str(self.model_path), n_samples=data.get("n_samples", 0))
            except Exception as e:
                logger.warning("ml_model_load_failed", error=str(e), path=str(self.model_path))
                self._init_new_model()
        else:
            self._init_new_model()

    def _init_new_model(self):
        """Initialize a new model."""
        self.model = IsolationForest(
            contamination=self.contamination,
            n_estimators=self.n_estimators,
            max_samples=self.max_samples,
            random_state=self.random_state,
            n_jobs=-1,
        )
        self.scaler = StandardScaler()
        logger.info("ml_model_initialized", contamination=self.contamination)

    def _extract_features(self, flow: dict[str, Any]) -> np.ndarray | None:
        """Extract numerical features from flow."""
        features = []
        for field in self.feature_fields:
            value = flow.get(field)
            if value is None:
                return None
            try:
                features.append(float(value))
            except (ValueError, TypeError):
                return None
        return np.array(features).reshape(1, -1)

    def _prepare_training_data(self, flows: list[dict[str, Any]]) -> np.ndarray | None:
        """Prepare training data from flows."""
        feature_matrix = []
        for flow in flows:
            features = self._extract_features(flow)
            if features is not None:
                feature_matrix.append(features.flatten())
        
        if len(feature_matrix) < 10:  # Need minimum samples
            return None
        
        return np.array(feature_matrix)

    async def train(self, flows: list[dict[str, Any]]) -> bool:
        """Train the model on historical flows."""
        X = self._prepare_training_data(flows)
        if X is None or len(X) < 10:
            logger.warning("ml_insufficient_training_data", count=len(X) if X is not None else 0)
            return False

        try:
            # Fit scaler
            X_scaled = self.scaler.fit_transform(X)
            
            # Train model
            self.model.fit(X_scaled)
            
            # Save model
            self._save_model(len(X))
            
            logger.info("ml_model_trained", n_samples=len(X), n_features=X.shape[1])
            return True
            
        except Exception as e:
            logger.exception("ml_training_failed", error=str(e))
            return False

    async def retrain_incremental(self, flow: dict[str, Any]) -> bool:
        """Add flow to training buffer and retrain if threshold reached."""
        features = self._extract_features(flow)
        if features is None:
            return False

        self._training_buffer.append(features.flatten())
        self._samples_since_retrain += 1

        if self._samples_since_retrain >= self.retrain_interval and len(self._training_buffer) >= 100:
            # Retrain with buffer data
            X = np.array(self._training_buffer)
            try:
                X_scaled = self.scaler.fit_transform(X)
                self.model.fit(X_scaled)
                self._save_model(len(X))
                self._training_buffer.clear()
                self._samples_since_retrain = 0
                logger.info("ml_model_retrained", n_samples=len(X))
                return True
            except Exception as e:
                logger.exception("ml_incremental_retrain_failed", error=str(e))
        
        return False

    def _save_model(self, n_samples: int):
        """Save model to disk."""
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({
            "model": self.model,
            "scaler": self.scaler,
            "feature_fields": self.feature_fields,
            "n_samples": n_samples,
            "contamination": self.contamination,
            "n_estimators": self.n_estimators,
        }, self.model_path)
        logger.debug("ml_model_saved", path=str(self.model_path))

    async def detect(self, flow: dict[str, Any]) -> MLDetectionResult | None:
        """Detect anomaly in a single flow."""
        if self.model is None or self.scaler is None:
            return None

        features = self._extract_features(flow)
        if features is None:
            return None

        try:
            # Scale features
            features_scaled = self.scaler.transform(features)
            
            # Predict
            prediction = self.model.predict(features_scaled)[0]  # -1 = anomaly, 1 = normal
            score = self.model.score_samples(features_scaled)[0]  # Lower = more anomalous
            
            is_anomaly = prediction == -1
            
            result = MLDetectionResult(
                is_anomaly=is_anomaly,
                score=float(score),
                threshold=self.contamination,
                features={field: float(features[0, i]) for i, field in enumerate(self.feature_fields)},
                metadata={
                    "model_type": "IsolationForest",
                    "contamination": self.contamination,
                },
            )
            
            if is_anomaly:
                logger.warning(
                    "ml_anomaly_detected",
                    score=score,
                    threshold=self.contamination,
                    features=result.features,
                )
            
            # Add to incremental retraining
            await self.retrain_incremental(flow)
            
            return result
            
        except Exception as e:
            logger.exception("ml_detection_failed", error=str(e))
            return None

    async def detect_batch(self, flows: list[dict[str, Any]]) -> list[MLDetectionResult | None]:
        """Detect anomalies in a batch of flows."""
        if self.model is None or self.scaler is None:
            return [None] * len(flows)

        # Extract features for all flows
        feature_matrix = []
        valid_indices = []
        
        for i, flow in enumerate(flows):
            features = self._extract_features(flow)
            if features is not None:
                feature_matrix.append(features.flatten())
                valid_indices.append(i)
        
        if not feature_matrix:
            return [None] * len(flows)

        X = np.array(feature_matrix)
        
        try:
            X_scaled = self.scaler.transform(X)
            predictions = self.model.predict(X_scaled)
            scores = self.model.score_samples(X_scaled)
            
            results = [None] * len(flows)
            for idx, (pred, score) in enumerate(zip(predictions, scores)):
                flow_idx = valid_indices[idx]
                is_anomaly = pred == -1
                
                features_dict = {
                    field: float(X[idx, i]) for i, field in enumerate(self.feature_fields)
                }
                
                results[flow_idx] = MLDetectionResult(
                    is_anomaly=is_anomaly,
                    score=float(score),
                    threshold=self.contamination,
                    features=features_dict,
                    metadata={
                        "model_type": "IsolationForest",
                        "contamination": self.contamination,
                    },
                )
                
                if is_anomaly:
                    logger.warning(
                        "ml_anomaly_detected",
                        score=score,
                        threshold=self.contamination,
                        features=features_dict,
                    )
            
            # Incremental retraining
            for flow in flows:
                await self.retrain_incremental(flow)
            
            return results
            
        except Exception as e:
            logger.exception("ml_batch_detection_failed", error=str(e))
            return [None] * len(flows)

    def get_stats(self) -> dict[str, Any]:
        """Get detector statistics."""
        return {
            "model_type": "IsolationForest",
            "model_loaded": self.model is not None,
            "scaler_fitted": self.scaler is not None and hasattr(self.scaler, 'mean_'),
            "contamination": self.contamination,
            "n_estimators": self.n_estimators,
            "feature_fields": self.feature_fields,
            "training_buffer_size": len(self._training_buffer),
            "samples_since_retrain": self._samples_since_retrain,
            "retrain_interval": self.retrain_interval,
            "model_path": str(self.model_path),
        }


def create_default_ml_detector() -> MLAnomalyDetector | None:
    """Create ML detector with default configuration from settings."""
    if not settings.detection.ml.enabled:
        return None
    
    return MLAnomalyDetector(
        model_path=settings.detection.ml.model_path,
        contamination=0.01,
    )