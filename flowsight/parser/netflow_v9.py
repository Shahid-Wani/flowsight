"""
NetFlow v9 Parser - Stub for Day 2

NetFlow v9 uses templates for flexible flow record formats.
"""

from typing import Any

from flowsight import get_logger

logger = get_logger(__name__)


class NetFlowV9Parser:
    """Parser for NetFlow v9 packets (template-based)."""
    
    def parse(self, data: bytes) -> list[dict[str, Any]]:
        """Parse NetFlow v9 packet - stub implementation."""
        logger.warning("netflow_v9_parser_not_implemented")
        return []


def parse_netflow_v9(data: bytes) -> list[dict[str, Any]]:
    """Convenience function to parse NetFlow v9."""
    parser = NetFlowV9Parser()
    return parser.parse(data)