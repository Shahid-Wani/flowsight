"""End-to-end tests for the flow collector.

Sends real UDP packets through a live collector and verifies flows
traverse the full pipeline into storage - the first true integration
test in the repo.
"""

import asyncio
import socket
import struct
from ipaddress import IPv4Address
from typing import Any

from flowsight.alerting.manager import AlertManager
from flowsight.alerting.threshold import AlertSeverity, ThresholdRule
from flowsight.collector.server import FlowCollector


class RecordingStorage:
    """Storage backend that records writes and signals receipt."""

    def __init__(self):
        self.flows: list[dict[str, Any]] = []
        self.received = asyncio.Event()

    async def write_flows(self, flows: list[dict[str, Any]]) -> int:
        self.flows.extend(flows)
        self.received.set()
        return len(flows)


def build_v5_packet(byte_count: int = 50000, packet_count: int = 100) -> bytes:
    """Build a valid NetFlow v5 packet with one flow record."""
    header = struct.pack(
        "!HHIIIIBBH",
        5,  # version
        1,  # flow count
        1000,  # sys uptime (ms)
        1725950000,  # unix secs
        0,  # unix nsecs
        42,  # flow sequence
        0,  # engine type
        0,  # engine id
        0,  # sampling interval
    )
    record = struct.pack(
        "!IIIHHIIIIHHBBBBHHBBH",
        int(IPv4Address("192.168.1.100")),  # src addr
        int(IPv4Address("10.0.0.1")),  # dst addr
        int(IPv4Address("0.0.0.0")),  # next hop
        1,  # input iface
        2,  # output iface
        packet_count,  # packets
        byte_count,  # bytes
        100,  # start time
        200,  # end time
        1234,  # src port
        80,  # dst port
        0,  # pad1
        0x1B,  # tcp flags
        6,  # protocol (TCP)
        0,  # tos
        65001,  # src as
        65002,  # dst as
        24,  # src mask
        24,  # dst mask
        0,  # pad2
    )
    return header + record


def make_pipeline(storage, alert_manager):
    from flowsight.pipeline import Pipeline

    return Pipeline(storage=storage, alert_manager=alert_manager)


async def test_collector_udp_end_to_end():
    """A v5 packet sent over UDP must land in storage with alerting live."""
    storage = RecordingStorage()
    alert_manager = AlertManager()
    alert_manager.add_custom_rule(
        ThresholdRule(
            name="e2e_high_bytes",
            field="bytes",
            operator=">",
            value=1000,
            severity=AlertSeverity.WARNING,
        )
    )
    collector = FlowCollector(
        host="127.0.0.1", port=0, pipeline=make_pipeline(storage, alert_manager), workers=1
    )
    await collector.start()

    try:
        sockname = collector._transport.get_extra_info("sockname")
        port = sockname[1]

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.settimeout(2)
            sock.sendto(build_v5_packet(byte_count=50000, packet_count=100), ("127.0.0.1", port))
        finally:
            sock.close()

        await asyncio.wait_for(storage.received.wait(), timeout=5)

        assert len(storage.flows) == 1
        flow = storage.flows[0]
        assert flow["src_ip"] == "192.168.1.100"
        assert flow["dst_ip"] == "10.0.0.1"
        assert flow["bytes"] == 50000
        assert flow["packets"] == 100

        # The threshold rule must have fired on the unified field name
        history = alert_manager.get_alert_history(limit=10)
        assert len(history) == 1
        assert history[0].rule_name == "e2e_high_bytes"
    finally:
        await asyncio.wait_for(collector.stop(), timeout=5)


async def test_collector_stop_does_not_hang_with_backlog():
    """stop() must return promptly even if packets remain queued."""
    storage = RecordingStorage()
    collector = FlowCollector(
        host="127.0.0.1", port=0, pipeline=make_pipeline(storage, AlertManager()), workers=1
    )
    await collector.start()

    # Stop the workers from draining by stuffing the queue beyond what
    # can be processed instantly, then stopping immediately.
    from flowsight.collector.server import FlowPacket

    for i in range(50):
        collector._queue.put_nowait(
            FlowPacket(
                data=b"",
                source_ip="127.0.0.1",
                source_port=9999,
                protocol="netflow_v5",
                timestamp=0.0,
                parsed_flows=[{"src_ip": "10.0.0.1", "bytes": i, "packets": 1}],
            )
        )

    await asyncio.wait_for(collector.stop(), timeout=10)
