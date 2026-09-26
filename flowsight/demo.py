"""Deterministic sample flow generation for local development."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

SOURCE_IPS = ("10.0.0.10", "10.0.0.11", "10.0.0.12")
DESTINATION_IPS = ("198.51.100.10", "203.0.113.20", "192.0.2.30")
PROTOCOLS = ((6, 443), (6, 80), (17, 53))


def generate_flows(count: int, seed: int = 42) -> list[dict[str, object]]:
    """Return reproducible flow records suitable for demos and tests."""
    if count < 1:
        raise ValueError("count must be at least 1")

    generator = random.Random(seed)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    flows: list[dict[str, object]] = []
    for index in range(count):
        protocol, destination_port = generator.choice(PROTOCOLS)
        flows.append(
            {
                "timestamp": (start + timedelta(minutes=index)).isoformat(),
                "src_ip": generator.choice(SOURCE_IPS),
                "dst_ip": generator.choice(DESTINATION_IPS),
                "src_port": generator.randint(32768, 60999),
                "dst_port": destination_port,
                "protocol": protocol,
                "duration": generator.randint(10, 3_600_000),
                "packets": generator.randint(1, 100),
                "bytes": generator.randint(512, 10_000_000),
            }
        )
    return flows
