"""
FlowSight Configuration Module

Uses Pydantic Settings for type-safe configuration management.
Supports YAML config files and environment variables.
"""

from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CollectorConfig(BaseSettings):
    """Flow collector configuration."""

    listen: str = "0.0.0.0:2055"
    protocols: list[Literal["netflow_v5", "netflow_v9", "ipfix", "sflow"]] = [
        "netflow_v5",
        "netflow_v9",
        "ipfix",
        "sflow",
    ]
    workers: int = 4
    buffer_size: int = 65536


class StorageConfig(BaseSettings):
    """Storage backend configuration."""

    type: Literal["influxdb", "timescaledb"] = "influxdb"
    url: str = "http://localhost:8086"
    org: str = "flowsight"
    bucket: str = "flows"
    token: str = ""
    batch_size: int = 5000
    flush_interval: int = 5


class EnrichmentConfig(BaseSettings):
    """IP enrichment configuration."""

    enabled: bool = True
    geoip_path: str = "./data/GeoLite2-City.mmdb"
    asn_path: str = "./data/GeoLite2-ASN.mmdb"
    abuseipdb_key: str = ""
    alienvault_otx_key: str = ""
    cache_ttl: int = 3600


class ThresholdRule(BaseSettings):
    """Threshold-based detection rule."""

    name: str
    field: str
    operator: Literal[">", "<", ">=", "<=", "==", "!="]
    value: float
    severity: Literal["info", "warning", "critical"] = "warning"


class ThresholdDetectionConfig(BaseSettings):
    """Threshold detection configuration."""

    enabled: bool = True
    rules: list[ThresholdRule] = []


class StatisticalDetectionConfig(BaseSettings):
    """Statistical anomaly detection configuration."""

    enabled: bool = True
    window: str = "5m"
    zscore_threshold: float = 3.0
    min_samples: int = 100


class MLDetectionConfig(BaseSettings):
    """ML-based anomaly detection configuration."""

    enabled: bool = False
    model_path: str = "./models/isolation_forest.pkl"
    retrain_interval: str = "24h"


class DetectionConfig(BaseSettings):
    """Anomaly detection configuration."""

    threshold: ThresholdDetectionConfig = ThresholdDetectionConfig()
    statistical: StatisticalDetectionConfig = StatisticalDetectionConfig()
    ml: MLDetectionConfig = MLDetectionConfig()


class APIConfig(BaseSettings):
    """REST API configuration."""

    host: str = "0.0.0.0"
    port: int = 8000
    jwt_secret: str = "change-me-in-production-use-strong-random"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]
    rate_limit: int = 100


class AlertHandlerConfig(BaseSettings):
    """Alert handler configuration."""

    type: Literal["log", "email", "webhook", "slack", "pagerduty"]
    url: str = ""
    headers: dict[str, str] = {}
    template: str = ""
    level: str = "info"


class AlertingConfig(BaseSettings):
    """Alerting configuration."""

    enabled: bool = True
    handlers: list[AlertHandlerConfig] = [AlertHandlerConfig(type="log", level="info")]


class LoggingConfig(BaseSettings):
    """Logging configuration."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    format: Literal["json", "console"] = "json"
    output: Literal["stdout", "stderr", "file"] = "stdout"
    file_path: str = "./logs/flowsight.log"
    max_bytes: int = 10485760
    backup_count: int = 5


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env", env_nested_delimiter="__", yaml_file="config.yaml", extra="ignore"
    )

    collector: CollectorConfig = CollectorConfig()
    storage: StorageConfig = StorageConfig()
    enrichment: EnrichmentConfig = EnrichmentConfig()
    detection: DetectionConfig = DetectionConfig()
    api: APIConfig = APIConfig()
    alerting: AlertingConfig = AlertingConfig()
    logging: LoggingConfig = LoggingConfig()

    @field_validator(
        "collector",
        "storage",
        "enrichment",
        "detection",
        "api",
        "alerting",
        "logging",
        mode="before",
    )
    @classmethod
    def _load_from_yaml(cls, v):
        """Allow nested config to be loaded from YAML."""
        return v


# Global settings instance
settings = Settings()


def load_config(config_path: str | Path | None = None) -> Settings:
    """Load configuration from file."""
    global settings
    if config_path:
        settings = Settings(_yaml_file=config_path)
    return settings
