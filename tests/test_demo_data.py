"""Tests for the deterministic demo flow generator."""

import pytest

from flowsight.demo import generate_flows

MIN_PACKETS = 1
MIN_BYTES = 512


def test_generate_flows_is_reproducible() -> None:
    """The same seed should produce identical records."""
    assert generate_flows(3, seed=7) == generate_flows(3, seed=7)


def test_generate_flows_has_expected_shape() -> None:
    """Generated records contain the fields consumed by the dashboard."""
    flow = generate_flows(1)[0]

    assert set(flow) == {
        "timestamp",
        "src_ip",
        "dst_ip",
        "src_port",
        "dst_port",
        "protocol",
        "duration",
        "packets",
        "bytes",
    }
    assert flow["src_ip"] in {"10.0.0.10", "10.0.0.11", "10.0.0.12"}
    assert flow["packets"] >= MIN_PACKETS
    assert flow["bytes"] >= MIN_BYTES


def test_generate_flows_rejects_non_positive_count() -> None:
    """A demo with no records is almost certainly a caller error."""
    with pytest.raises(ValueError, match="count must be at least 1"):
        generate_flows(0)
