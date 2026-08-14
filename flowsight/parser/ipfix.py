"""
IPFIX Parser - Stub for Day 2

IPFIX (IP Flow Information Export) is based on NetFlow v9.
"""

from typing import Any

from flowsight import get_logger

logger = get_logger(__name__)


class IPFIXParser:
    """Parser for IPFIX packets."""
    
    def parse(self, data: bytes) -> list[dict[str, Any]]:
        """Parse IPFIX packet - stub implementation."""
        logger.warning("ipfix_parser_not_implemented")
        return []


def parse_ipfix(data: bytes) -> list[dict[str, Any]]:
    """Convenience function to parse IPFIX."""
    parser = IPFIXParser()
    return parser.parse(data)