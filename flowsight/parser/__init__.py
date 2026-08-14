"""
FlowSight Parser Module

Parsers for NetFlow v5/v9, IPFIX, and sFlow.
"""

from flowsight.parser.netflow_v5 import NetFlowV5Parser, parse_netflow_v5
from flowsight.parser.netflow_v9 import NetFlowV9Parser, parse_netflow_v9
from flowsight.parser.ipfix import IPFIXParser, parse_ipfix
from flowsight.parser.sflow import SFlowParser, parse_sflow

__all__ = [
    "NetFlowV5Parser",
    "parse_netflow_v5",
    "NetFlowV9Parser", 
    "parse_netflow_v9",
    "IPFIXParser",
    "parse_ipfix",
    "SFlowParser",
    "parse_sflow",
    "parse_flow_packet",
]


def parse_flow_packet(data: bytes) -> list[dict] | None:
    """Auto-detect and parse flow packet."""
    if len(data) < 4:
        return None
    
    version = int.from_bytes(data[:2], "big")
    
    if version == 5:
        return parse_netflow_v5(data)
    elif version == 9:
        return parse_netflow_v9(data)
    elif version == 10:  # IPFIX
        return parse_ipfix(data)
    # sFlow doesn't have a fixed version in the same way
    # Try sFlow as fallback
    try:
        return parse_sflow(data)
    except Exception:
        pass
    
    return None