"""
IPFIX Parser

Uses the NetFlow v9/IPFIX parser implementation.
"""

from flowsight.parser.netflow_v9 import NetFlowV9IPFIXParser, parse_ipfix

# Re-export for backward compatibility
IPFIXParser = NetFlowV9IPFIXParser

__all__ = ["IPFIXParser", "parse_ipfix"]