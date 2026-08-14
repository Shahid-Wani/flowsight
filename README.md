# FlowSight - NetFlow/sFlow/IPFIX Analyzer

Open-source network flow analyzer for bandwidth visibility & threat hunting.

## Architecture

```
Network Devices → Flow Collector → Processing Pipeline → InfluxDB
                                            ↓
                                    Enrichment (GeoIP, ASN, Threat Intel)
                                            ↓
                                    Anomaly Detection
                                            ↓
                                    Alerting → Dashboard
```

## Features

- **Multi-format collector**: NetFlow v5/v9, IPFIX, sFlow
- **Real-time dashboard**: Bandwidth, top talkers, geo-map, anomalies
- **Anomaly detection**: Threshold, statistical (z-score), ML (IsolationForest)
- **Threat intelligence**: AbuseIPDB, AlienVault OTX integration
- **Alerting**: Email, Slack, Webhook, PagerDuty
- **Multi-tenant**: Organizations, RBAC, data isolation

## Quick Start

```bash
# Start with Docker Compose (includes InfluxDB)
docker compose up -d

# Or run locally
pip install -e .
flowsight-collector --config config.yaml
flowsight-api --config config.yaml
```

## Configuration

Copy `config.example.yaml` to `config.yaml` and adjust:

```yaml
collector:
  listen: "0.0.0.0:2055"
  protocols: ["netflow_v5", "netflow_v9", "ipfix", "sflow"]

storage:
  type: "influxdb"
  url: "http://localhost:8086"
  org: "flowsight"
  bucket: "flows"
  token: "your-token"

enrichment:
  geoip_path: "./data/GeoLite2-City.mmdb"
  asn_path: "./data/GeoLite2-ASN.mmdb"
  abuseipdb_key: ""  # optional

detection:
  threshold:
    enabled: true
    rules:
      - name: "high_bandwidth"
        field: "bytes"
        operator: ">"
        value: 100000000  # 100 MB
  statistical:
    enabled: true
    window: "5m"
    zscore_threshold: 3.0
  ml:
    enabled: false
    model_path: "./models/isolation_forest.pkl"

api:
  host: "0.0.0.0"
  port: 8000
  jwt_secret: "change-me-in-production"
  cors_origins: ["http://localhost:3000"]

alerting:
  handlers:
    - type: "webhook"
      url: "https://hooks.slack.com/services/xxx"
```

## Project Structure

```
flowsight/
├── collector/       # UDP flow collectors
├── parser/          # NetFlow/IPFIX/sFlow parsers
├── storage/         # InfluxDB/TimescaleDB writers
├── enrichment/      # GeoIP, ASN, Threat Intel
├── detection/       # Anomaly detection engines
├── alerting/        # Alert handlers
├── api/             # FastAPI REST + WebSocket
├── dashboard/       # React frontend (separate repo)
├── tests/           # Unit & integration tests
├── scripts/         # Utility scripts
└── docs/            # Documentation
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/

# Run linting
ruff check .
mypy flowsight/

# Generate demo data
python scripts/generate_demo_data.py
```

## License

MIT License - see LICENSE file