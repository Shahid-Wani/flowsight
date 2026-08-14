"""
NetFlow v5 Parser

NetFlow v5 is a fixed-format protocol with 24-byte header and 48-byte flow records.
"""

import socket
import struct
from typing import Any

from flowsight import get_logger

logger = get_logger(__name__)


class NetFlowV5Parser:
    """Parser for NetFlow v5 packets."""

    # Header: version(2) count(2) sys_uptime(4) unix_secs(4) unix_nsecs(4)
    # flow_sequence(4) engine_type(1) engine_id(1) sampling_interval(2)
    HEADER_FORMAT = "!HHIIIIBBH"
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

    # Flow record: src_addr(4) dst_addr(4) next_hop(4) input_iface(2) output_iface(2)
    # packet_count(4) byte_count(4) start_time(4) end_time(4)
    # src_port(2) dst_port(2) pad1(1) tcp_flags(1) proto(1) tos(1)
    # src_as(2) dst_as(2) src_mask(1) dst_mask(1) pad2(2)
    FLOW_FORMAT = "!IIIHHIIIIHHBBBBHHBBH"
    FLOW_SIZE = struct.calcsize(FLOW_FORMAT)

    def parse(self, data: bytes) -> list[dict[str, Any]]:
        """Parse NetFlow v5 packet."""
        if len(data) < self.HEADER_SIZE:
            logger.warning("netflow_v5_packet_too_short", length=len(data))
            return []

        try:
            header = struct.unpack(self.HEADER_FORMAT, data[: self.HEADER_SIZE])
        except struct.error as e:
            logger.warning("netflow_v5_header_unpack_failed", error=str(e))
            return []

        (
            version,
            count,
            sys_uptime,
            unix_secs,
            unix_nsecs,
            flow_sequence,
            engine_type,
            engine_id,
            sampling_interval,
        ) = header

        if version != 5:
            logger.warning("netflow_v5_wrong_version", version=version)
            return []

        flows = []
        offset = self.HEADER_SIZE

        for i in range(count):
            if offset + self.FLOW_SIZE > len(data):
                logger.warning(
                    "netflow_v5_truncated_flow", flow_index=i, remaining=len(data) - offset
                )
                break

            try:
                flow_data = struct.unpack(self.FLOW_FORMAT, data[offset : offset + self.FLOW_SIZE])
            except struct.error as e:
                logger.warning("netflow_v5_flow_unpack_failed", flow_index=i, error=str(e))
                break

            offset += self.FLOW_SIZE

            (
                src_addr,
                dst_addr,
                next_hop,
                input_iface,
                output_iface,
                packet_count,
                byte_count,
                start_time,
                end_time,
                src_port,
                dst_port,
                pad1,
                tcp_flags,
                proto,
                tos,
                src_as,
                dst_as,
                src_mask,
                dst_mask,
                pad2,
            ) = flow_data

            # Convert IPs from network byte order
            src_ip = socket.inet_ntoa(struct.pack("!I", src_addr))
            dst_ip = socket.inet_ntoa(struct.pack("!I", dst_addr))
            next_hop_ip = socket.inet_ntoa(struct.pack("!I", next_hop))

            flow = {
                "version": 5,
                "src_ip": src_ip,
                "dst_ip": dst_ip,
                "next_hop": next_hop_ip,
                "input_interface": input_iface,
                "output_interface": output_iface,
                "packet_count": packet_count,
                "byte_count": byte_count,
                "start_time": start_time,
                "end_time": end_time,
                "src_port": src_port,
                "dst_port": dst_port,
                "tcp_flags": tcp_flags,
                "protocol": proto,
                "tos": tos,
                "src_as": src_as,
                "dst_as": dst_as,
                "src_mask": src_mask,
                "dst_mask": dst_mask,
                "sys_uptime": sys_uptime,
                "unix_secs": unix_secs,
                "unix_nsecs": unix_nsecs,
                "flow_sequence": flow_sequence,
                "engine_type": engine_type,
                "engine_id": engine_id,
                "sampling_interval": sampling_interval,
            }
            flows.append(flow)

        logger.debug("netflow_v5_parsed", flow_count=len(flows), sequence=flow_sequence)
        return flows


def parse_netflow_v5(data: bytes) -> list[dict[str, Any]]:
    """Convenience function to parse NetFlow v5."""
    parser = NetFlowV5Parser()
    return parser.parse(data)
