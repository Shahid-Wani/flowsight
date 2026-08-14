"""
FlowSight Parser Module

Parsers for NetFlow v5/v9, IPFIX, and sFlow.
"""

from flowsight.parser.ipfix import IPFIXParser, parse_ipfix
from flowsight.parser.netflow_v5 import NetFlowV5Parser, parse_netflow_v5
from flowsight.parser.netflow_v9 import NetFlowV9IPFIXParser, parse_netflow_v9
from flowsight.parser.sflow import SFlowParser, parse_sflow

__all__ = [
    "IPFIXParser",
    "NetFlowV5Parser",
    "NetFlowV9IPFIXParser",
    "SFlowParser",
    "parse_flow_packet",
    "parse_ipfix",
    "parse_netflow_v5",
    "parse_netflow_v9",
    "parse_sflow",
]


def parse_flow_packet(data: bytes) -> list[dict] | None:
    """Auto-detect and parse flow packet."""
    if len(data) < 4:
        return None

    version = int.from_bytes(data[:2], "big")

    if version == 5:
        return parse_netflow_v5(data)
    if version == 9:
        return parse_netflow_v9(data)
    if version == 10:  # IPFIX
        return parse_ipfix(data)
    # sFlow doesn't have a fixed version in the same way
    # Try sFlow as fallback
    try:
        return parse_sflow(data)
    except Exception:
        pass

    return None
