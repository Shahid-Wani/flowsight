# FlowSight - NetFlow/sFlow/IPFIX Analyzer

[![CI](https://github.com/Shahid-Wani/flowsight/actions/workflows/ci.yml/badge.svg)](https://github.com/Shahid-Wani/flowsight/actions/workflows/ci.yml)

Open-source network flow analyzer for bandwidth visibility & threat hunting.

FlowSight turns NetFlow, sFlow, and IPFIX telemetry into searchable flow records,
enriched context, anomaly signals, and actionable alerts.

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
- **Processing pipeline**: enrichment → storage → detection → alerting, failure-isolated per stage
- **Real-time dashboard**: Bandwidth, top talkers, geo-map, alerts
- **Anomaly detection**: Threshold rules, statistical (z-score); ML (IsolationForest) available via model training
- **Enrichment**: GeoIP (MaxMind GeoLite2), ASN, threat intel (AbuseIPDB, AlienVault OTX)
- **Alerting**: Log, Webhook, Email handlers

## Quick Start

```bash
# Start with Docker Compose (includes InfluxDB + dashboard)
docker compose up -d

# Or run locally
pip install -e .
cp config.example.yaml config.yaml
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
├── storage/         # InfluxDB writers
├── enrichment/      # GeoIP, ASN, Threat Intel
├── detection/       # Anomaly detection engines
├── alerting/        # Alert handlers
├── api/             # FastAPI REST + WebSocket
├── dashboard/       # React frontend
├── tests/           # Unit & integration tests
└── scripts/         # Utility scripts
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
python scripts/generate_demo_data.py --count 1000 --output demo-flows.json

# Enrich and analyze demo flows
flowsight-enrich -i demo-flows.json -o enriched-flows.json
flowsight-detect -i demo-flows.json
```

## License

MIT License - see LICENSE file