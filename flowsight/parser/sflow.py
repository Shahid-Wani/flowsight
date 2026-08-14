"""
sFlow Parser

sFlow (sampled Flow) is a packet sampling technology for network monitoring.
Unlike NetFlow, sFlow samples packets at the interface level and exports
sampled packet headers + interface counters.

sFlow v5 datagram structure:
- Datagram header
- Flow samples (multiple)
- Counter samples (multiple)
"""

import struct
from dataclasses import dataclass
from typing import Any

from flowsight import get_logger

logger = get_logger(__name__)

# sFlow v5 constants
SFLOW_VERSION = 5
SFLOW_HEADER_SIZE = 24  # version(4) + agent_ip(4) + sub_agent_id(4) + sequence(4) + uptime(4) + samples(4)

# Sample types
FLOW_SAMPLE = 1
COUNTER_SAMPLE = 2
EXPANDED_FLOW_SAMPLE = 3
EXPANDED_COUNTER_SAMPLE = 4

# Flow sample types (enterprise 0)
FLOW_SAMPLE_RAW_PACKET = 1
FLOW_SAMPLE_ETHERNET = 2
FLOW_SAMPLE_IPV4 = 3
FLOW_SAMPLE_IPV6 = 4
FLOW_SAMPLE_EXTENDED_SWITCH = 1001
FLOW_SAMPLE_EXTENDED_ROUTER = 1002
FLOW_SAMPLE_EXTENDED_GATEWAY = 1003
FLOW_SAMPLE_EXTENDED_USER = 1004
FLOW_SAMPLE_EXTENDED_URL = 1005
FLOW_SAMPLE_EXTENDED_MPLS = 1006
FLOW_SAMPLE_EXTENDED_NAT = 1007
FLOW_SAMPLE_EXTENDED_MPLS_TUNNEL = 1008
FLOW_SAMPLE_EXTENDED_MPLS_VC = 1009
FLOW_SAMPLE_EXTENDED_MPLS_FEC = 1010
FLOW_SAMPLE_EXTENDED_MPLS_LVP_FEC = 1011
FLOW_SAMPLE_EXTENDED_VLAN_TUNNEL = 1012

# Counter sample types
COUNTER_SAMPLE_GENERIC = 1
COUNTER_SAMPLE_ETHERNET = 2
COUNTER_SAMPLE_TOKEN_RING = 3
COUNTER_SAMPLE_100BASEVG = 4
COUNTER_SAMPLE_VLAN = 5
COUNTER_SAMPLE_PROCESSOR = 1001
COUNTER_SAMPLE_RADIO = 1002
COUNTER_SAMPLE_RADIO_RECEIVER = 1003
COUNTER_SAMPLE_RADIO_TRANSMITTER = 1004
COUNTER_SAMPLE_RADIO_ANTENNA = 1005


@dataclass
class SFlowDatagram:
    """Parsed sFlow datagram."""
    version: int
    agent_ip: str
    sub_agent_id: int
    sequence_number: int
    uptime: int
    flow_samples: list[dict[str, Any]]
    counter_samples: list[dict[str, Any]]


class SFlowParser:
    """Parser for sFlow v5 datagrams."""

    def __init__(self):
        pass

    def can_handle(self, data: bytes) -> bool:
        """Check if this is an sFlow datagram."""
        if len(data) < 4:
            return False
        version = struct.unpack("!I", data[:4])[0]
        return version == SFLOW_VERSION

    def parse(self, data: bytes, source_ip: str, source_port: int) -> list[dict[str, Any]]:
        """Parse sFlow v5 datagram."""
        if len(data) < SFLOW_HEADER_SIZE:
            logger.warning("sflow_datagram_too_short", length=len(data))
            return []

        try:
            datagram = self._parse_datagram(data, source_ip, source_port)
        except struct.error as e:
            logger.warning("sflow_parse_failed", error=str(e))
            return []

        flows = []
        
        # Convert flow samples to flow records
        for sample in datagram.flow_samples:
            flow = self._flow_sample_to_record(sample, datagram)
            if flow:
                flows.append(flow)

        logger.debug("sflow_parsed", source_ip=source_ip, flow_count=len(flows), sequence=datagram.sequence_number)
        return flows

    def _parse_datagram(self, data: bytes, source_ip: str, source_port: int) -> SFlowDatagram:
        """Parse sFlow datagram header and samples."""
        # Header: version(4) agent_ip(4) sub_agent_id(4) sequence(4) uptime(4) sample_count(4)
        header_fmt = "!IIIIII"
        header_size = struct.calcsize(header_fmt)
        
        version, agent_addr, sub_agent_id, sequence_number, uptime, sample_count = struct.unpack(
            header_fmt, data[:header_size]
        )

        # Convert agent IP
        agent_ip = self._bytes_to_ip(agent_addr)

        offset = header_size
        flow_samples = []
        counter_samples = []

        for _ in range(sample_count):
            if offset + 8 > len(data):
                break

            sample_type, sample_length = struct.unpack("!II", data[offset:offset + 8])
            offset += 8

            if sample_length < 8:
                logger.warning("sflow_invalid_sample_length", length=sample_length)
                break

            sample_data = data[offset:offset + sample_length - 8]
            offset += sample_length - 8

            # Align to 4-byte boundary
            offset = (offset + 3) & ~3

            if sample_type == FLOW_SAMPLE:
                flow_samples.append(self._parse_flow_sample(sample_data))
            elif sample_type == COUNTER_SAMPLE:
                counter_samples.append(self._parse_counter_sample(sample_data))
            elif sample_type == EXPANDED_FLOW_SAMPLE:
                flow_samples.append(self._parse_expanded_flow_sample(sample_data))
            elif sample_type == EXPANDED_COUNTER_SAMPLE:
                counter_samples.append(self._parse_expanded_counter_sample(sample_data))

        return SFlowDatagram(
            version=version,
            agent_ip=agent_ip,
            sub_agent_id=sub_agent_id,
            sequence_number=sequence_number,
            uptime=uptime,
            flow_samples=flow_samples,
            counter_samples=counter_samples,
        )

    def _parse_flow_sample(self, data: bytes) -> dict[str, Any]:
        """Parse a standard flow sample (enterprise=0, format=1)."""
        if len(data) < 48:
            return {}

        # Flow sample header: sequence(4) source_id_type(4) source_id(4) sampling_rate(4)
        # sample_pool(4) drops(4) input(4) output(4) flow_records(4)
        header_fmt = "!IIIIIIIII"
        header_size = struct.calcsize(header_fmt)

        (sequence_number, source_id_type, source_id_index, sampling_rate,
         sample_pool, drops, input_iface, output_iface, flow_records) = struct.unpack(
            header_fmt, data[:header_size]
        )

        offset = header_size
        records = []

        for _ in range(flow_records):
            if offset + 8 > len(data):
                break

            format_type, format_length = struct.unpack("!II", data[offset:offset + 8])
            offset += 8

            record_data = data[offset:offset + format_length - 8]
            offset += format_length - 8

            # Align
            offset = (offset + 3) & ~3

            if format_type == FLOW_SAMPLE_RAW_PACKET:
                records.append(self._parse_raw_packet(record_data))
            elif format_type == FLOW_SAMPLE_ETHERNET:
                records.append(self._parse_ethernet(record_data))
            elif format_type == FLOW_SAMPLE_IPV4:
                records.append(self._parse_ipv4(record_data))
            elif format_type == FLOW_SAMPLE_IPV6:
                records.append(self._parse_ipv6(record_data))
            elif format_type >= 1000:  # Extended formats
                records.append(self._parse_extended_flow(record_data, format_type))

        return {
            "sequence_number": sequence_number,
            "source_id_type": source_id_type,
            "source_id_index": source_id_index,
            "sampling_rate": sampling_rate,
            "sample_pool": sample_pool,
            "drops": drops,
            "input_interface": input_iface,
            "output_interface": output_iface,
            "records": records,
        }

    def _parse_raw_packet(self, data: bytes) -> dict[str, Any]:
        """Parse raw packet header sample."""
        if len(data) < 12:
            return {}

        header_protocol, frame_length, stripped_bytes, header_length = struct.unpack("!IIII", data[:16])
        header_bytes = data[16:16 + header_length]

        return {
            "format": "raw_packet",
            "header_protocol": header_protocol,
            "frame_length": frame_length,
            "stripped_bytes": stripped_bytes,
            "header_length": header_length,
            "header_bytes": header_bytes.hex() if header_bytes else "",
        }

    def _parse_ethernet(self, data: bytes) -> dict[str, Any]:
        """Parse Ethernet frame sample."""
        if len(data) < 4:
            return {}

        eth_length = struct.unpack("!I", data[:4])[0]
        eth_data = data[4:4 + eth_length]

        # Parse MAC addresses if present
        src_mac = dst_mac = ""
        eth_proto = 0
        if len(eth_data) >= 14:
            dst_mac = ":".join(f"{b:02x}" for b in eth_data[0:6])
            src_mac = ":".join(f"{b:02x}" for b in eth_data[6:12])
            eth_proto = struct.unpack("!H", eth_data[12:14])[0]

        return {
            "format": "ethernet",
            "src_mac": src_mac,
            "dst_mac": dst_mac,
            "eth_protocol": eth_proto,
            "length": eth_length,
        }

    def _parse_ipv4(self, data: bytes) -> dict[str, Any]:
        """Parse IPv4 packet sample."""
        if len(data) < 20:
            return {}

        # IPv4 header: version/ihl(1) tos(1) length(2) id(2) flags/frag(2) ttl(1) proto(1) checksum(2)
        # src(4) dst(4)
        ihl = data[0] & 0x0F
        header_len = ihl * 4
        
        if len(data) < header_len:
            return {}

        tos = data[1]
        total_length = struct.unpack("!H", data[2:4])[0]
        identification = struct.unpack("!H", data[4:6])[0]
        flags_fragment = struct.unpack("!H", data[6:8])[0]
        ttl = data[8]
        protocol = data[9]
        src_ip = struct.unpack("!I", data[12:16])[0]
        dst_ip = struct.unpack("!I", data[16:20])[0]

        # Convert IPs
        import socket
        src_ip_str = socket.inet_ntoa(struct.pack("!I", src_ip))
        dst_ip_str = socket.inet_ntoa(struct.pack("!I", dst_ip))

        # Extract ports if TCP/UDP
        src_port = dst_port = 0
        tcp_flags = 0
        if protocol in (6, 17) and len(data) >= header_len + 4:
            # TCP/UDP header starts at header_len
            transport_offset = header_len
            if len(data) >= transport_offset + 4:
                src_port = struct.unpack("!H", data[transport_offset:transport_offset + 2])[0]
                dst_port = struct.unpack("!H", data[transport_offset + 2:transport_offset + 4])[0]
            if protocol == 6 and len(data) >= transport_offset + 13:
                # TCP flags at offset 13
                tcp_flags = data[transport_offset + 13]

        return {
            "format": "ipv4",
            "src_ip": src_ip_str,
            "dst_ip": dst_ip_str,
            "protocol": protocol,
            "tos": tos,
            "ttl": ttl,
            "length": total_length,
            "identification": identification,
            "flags": flags_fragment >> 13,
            "fragment_offset": flags_fragment & 0x1FFF,
            "src_port": src_port,
            "dst_port": dst_port,
            "tcp_flags": tcp_flags,
        }

    def _parse_ipv6(self, data: bytes) -> dict[str, Any]:
        """Parse IPv6 packet sample."""
        if len(data) < 40:
            return {}

        # IPv6 header: version/traffic_class/flow_label(4) payload_length(2) next_header(1) hop_limit(1)
        # src(16) dst(16)
        version_tc_fl = struct.unpack("!I", data[:4])[0]
        version = (version_tc_fl >> 28) & 0xF
        traffic_class = (version_tc_fl >> 20) & 0xFF
        flow_label = version_tc_fl & 0xFFFFF

        payload_length = struct.unpack("!H", data[4:6])[0]
        next_header = data[6]
        hop_limit = data[7]

        import socket
        src_ip = socket.inet_ntop(socket.AF_INET6, data[8:24])
        dst_ip = socket.inet_ntop(socket.AF_INET6, data[24:40])

        # Parse extension headers / transport
        src_port = dst_port = 0
        tcp_flags = 0
        offset = 40
        nh = next_header

        # Simple parsing for TCP/UDP
        while nh in (0, 43, 44, 50, 51, 60) and offset + 8 <= len(data):  # Hop-by-hop, Routing, Fragment, ESP, AH, Destination
            next_nh = data[offset]
            ext_len = (data[offset + 1] + 1) * 8
            nh = next_nh
            offset += ext_len

        if nh in (6, 17) and offset + 4 <= len(data):  # TCP/UDP
            src_port = struct.unpack("!H", data[offset:offset + 2])[0]
            dst_port = struct.unpack("!H", data[offset + 2:offset + 4])[0]
            if nh == 6 and offset + 13 < len(data):
                tcp_flags = data[offset + 13]

        return {
            "format": "ipv6",
            "src_ip": src_ip,
            "dst_ip": dst_ip,
            "next_header": next_header,
            "hop_limit": hop_limit,
            "traffic_class": traffic_class,
            "flow_label": flow_label,
            "payload_length": payload_length,
            "src_port": src_port,
            "dst_port": dst_port,
            "tcp_flags": tcp_flags,
        }

    def _parse_extended_flow(self, data: bytes, format_type: int) -> dict[str, Any]:
        """Parse extended flow formats (switch, router, gateway, etc.)."""
        return {
            "format": f"extended_{format_type}",
            "data_length": len(data),
        }

    def _parse_counter_sample(self, data: bytes) -> dict[str, Any]:
        """Parse standard counter sample."""
        if len(data) < 12:
            return {}

        sequence_number, source_id_type, source_id_index = struct.unpack("!III", data[:12])
        offset = 12

        counters = []
        while offset + 8 <= len(data):
            counter_type, counter_length = struct.unpack("!II", data[offset:offset + 8])
            offset += 8

            counter_data = data[offset:offset + counter_length - 8]
            offset += counter_length - 8
            offset = (offset + 3) & ~3

            counters.append(self._parse_counter_record(counter_data, counter_type))

        return {
            "sequence_number": sequence_number,
            "source_id_type": source_id_type,
            "source_id_index": source_id_index,
            "counters": counters,
        }

    def _parse_expanded_flow_sample(self, data: bytes) -> dict[str, Any]:
        """Parse expanded flow sample (with enterprise ID)."""
        if len(data) < 12:
            return {}

        sequence_number, source_id_type, source_id_index = struct.unpack("!III", data[:12])
        # enterprise_id = struct.unpack("!I", data[12:16])[0]  # Next 4 bytes
        # Same as flow sample but with enterprise
        return self._parse_flow_sample(data[12:])

    def _parse_expanded_counter_sample(self, data: bytes) -> dict[str, Any]:
        """Parse expanded counter sample."""
        return self._parse_counter_sample(data)

    def _parse_counter_record(self, data: bytes, counter_type: int) -> dict[str, Any]:
        """Parse a single counter record."""
        result = {"type": counter_type}

        if counter_type == COUNTER_SAMPLE_GENERIC and len(data) >= 72:
            # Generic interface counters
            (if_index, if_type, if_speed, if_direction, if_status,
             in_octets, in_unicast_pkts, in_multicast_pkts, in_broadcast_pkts,
             in_discards, in_errors, in_unknown_protos,
             out_octets, out_unicast_pkts, out_multicast_pkts, out_broadcast_pkts,
             out_discards, out_errors, out_promiscuous) = struct.unpack("!IIIIIQQQQQQQQQQQQ", data[:144])
            result.update({
                "if_index": if_index,
                "if_type": if_type,
                "if_speed": if_speed,
                "if_direction": if_direction,
                "if_status": if_status,
                "in_octets": in_octets,
                "in_unicast_pkts": in_unicast_pkts,
                "in_multicast_pkts": in_multicast_pkts,
                "in_broadcast_pkts": in_broadcast_pkts,
                "in_discards": in_discards,
                "in_errors": in_errors,
                "in_unknown_protos": in_unknown_protos,
                "out_octets": out_octets,
                "out_unicast_pkts": out_unicast_pkts,
                "out_multicast_pkts": out_multicast_pkts,
                "out_broadcast_pkts": out_broadcast_pkts,
                "out_discards": out_discards,
                "out_errors": out_errors,
            })
        elif counter_type == COUNTER_SAMPLE_ETHERNET and len(data) >= 48:
            (alignment_errors, fcs_errors, single_collision_frames,
             multiple_collision_frames, sqe_test_errors, deferred_transmissions,
             late_collisions, excessive_collisions, internal_mac_transmit_errors,
             carrier_sense_errors, frame_too_long, frame_too_short,
             internal_mac_receive_errors) = struct.unpack("!QQQQQQQQQQQQQ", data[:104])
            result.update({
                "alignment_errors": alignment_errors,
                "fcs_errors": fcs_errors,
                "single_collision_frames": single_collision_frames,
                "multiple_collision_frames": multiple_collision_frames,
                "late_collisions": late_collisions,
                "excessive_collisions": excessive_collisions,
            })

        return result

    def _flow_sample_to_record(self, sample: dict[str, Any], datagram: SFlowDatagram) -> dict[str, Any] | None:
        """Convert a flow sample to a flow record compatible with our storage."""
        if not sample.get("records"):
            return None

        # Use the first record (typically IPv4/IPv6)
        record = sample["records"][0]

        flow = {
            "version": "sflow",
            "source_ip": datagram.agent_ip,
            "source_port": datagram.sub_agent_id,
            "sampling_rate": sample.get("sampling_rate", 1),
            "input_interface": sample.get("input_interface", 0),
            "output_interface": sample.get("output_interface", 0),
            "sequence_number": datagram.sequence_number,
            "uptime": datagram.uptime,
        }

        # Map record fields
        if record.get("format") in ("ipv4", "ipv6"):
            flow.update({
                "src_ip": record.get("src_ip"),
                "dst_ip": record.get("dst_ip"),
                "protocol": record.get("protocol"),
                "src_port": record.get("src_port", 0),
                "dst_port": record.get("dst_port", 0),
                "tcp_flags": record.get("tcp_flags", 0),
                "tos": record.get("tos", 0),
                "ttl": record.get("ttl", 0),
                "length": record.get("length", 0),
            })
        elif record.get("format") == "ethernet":
            flow.update({
                "src_mac": record.get("src_mac"),
                "dst_mac": record.get("dst_mac"),
                "eth_protocol": record.get("eth_protocol", 0),
            })

        return flow

    def _bytes_to_ip(self, addr: int) -> str:
        """Convert 32-bit integer to IP string."""
        import socket
        return socket.inet_ntoa(struct.pack("!I", addr))


def parse_sflow(data: bytes, source_ip: str = "", source_port: int = 0) -> list[dict[str, Any]]:
    """Convenience function to parse sFlow."""
    parser = SFlowParser()
    return parser.parse(data, source_ip, source_port)