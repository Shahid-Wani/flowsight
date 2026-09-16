"""IP protocol number to name mapping for API responses."""

from typing import Any

PROTOCOL_NAMES: dict[int, str] = {
    1: "ICMP",
    2: "IGMP",
    6: "TCP",
    17: "UDP",
    41: "IPv6",
    47: "GRE",
    50: "ESP",
    51: "AH",
    58: "ICMPv6",
    89: "OSPF",
    132: "SCTP",
}


def protocol_name(value: Any) -> str:
    """Map a protocol number (or name) to its display name.

    Numeric values (or numeric strings, as InfluxDB tags are strings)
    resolve via PROTOCOL_NAMES; non-numeric values pass through.
    """
    if value is None or value == "":
        return "Unknown"
    try:
        number = int(value)
    except (TypeError, ValueError):
        return str(value)
    return PROTOCOL_NAMES.get(number, f"Proto {number}")
