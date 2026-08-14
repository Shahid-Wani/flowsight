"""
sFlow Parser - Stub for Day 2

sFlow (sampled Flow) is a different protocol from NetFlow.
"""

from typing import Any

from flowsight import get_logger

logger = get_logger(__name__)


class SFlowParser:
    """Parser for sFlow packets."""
    
    def parse(self, data: bytes) -> list[dict[str, Any]]:
        """Parse sFlow packet - stub implementation."""
        logger.warning("sflow_parser_not_implemented")
        return []


def parse_sflow(data: bytes) -> list[dict[str, Any]]:
    """Convenience function to parse sFlow."""
    parser = SFlowParser()
    return parser.parse(data)