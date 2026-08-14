"""
NetFlow v9 / IPFIX Parser

Template-based flow parsing for NetFlow v9 and IPFIX protocols.
Both protocols use the same template mechanism.
"""

import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from flowsight import get_logger

logger = get_logger(__name__)

# NetFlow v9 / IPFIX Field Types (IANA assigned)
# https://www.iana.org/assignments/ipfix/ipfix.xhtml
class FieldType:
    """Common NetFlow v9 / IPFIX field types."""
    # NetFlow v9 fields
    IN_BYTES = 1
    IN_PACKETS = 2
    FLOWS = 3
    IN_PROTOCOL = 4
    IPV4_SRC_ADDR = 8
    IPV4_DST_ADDR = 12
    IPV4_NEXT_HOP = 15
    INPUT_SNMP = 10
    OUTPUT_SNMP = 14
    L4_SRC_PORT = 7
    L4_DST_PORT = 11
    TCP_FLAGS = 6
    PROTOCOL = 4
    IP_TOS = 5
    SRC_AS = 16
    DST_AS = 17
    SRC_MASK = 9
    DST_MASK = 13
    FIRST_SWITCHED = 22
    LAST_SWITCHED = 21
    
    # IPFIX additional fields
    OCTET_DELTA_COUNT = 1
    PACKET_DELTA_COUNT = 2
    FLOW_START_MILLISECONDS = 150
    FLOW_END_MILLISECONDS = 151
    FLOW_START_MICROSECONDS = 152
    FLOW_END_MICROSECONDS = 153
    FLOW_START_NANOSECONDS = 154
    FLOW_END_NANOSECONDS = 155
    FLOW_START_DELTA_MICROSECONDS = 156
    FLOW_END_DELTA_MICROSECONDS = 157
    FLOW_START_DELTA_NANOSECONDS = 158
    FLOW_END_DELTA_NANOSECONDS = 159
    FLOW_DURATION_MILLISECONDS = 160
    FLOW_DURATION_MICROSECONDS = 161
    FLOW_DURATION_NANOSECONDS = 162
    BIFLOW_DIRECTION = 239
    IPV6_SRC_ADDR = 27
    IPV6_DST_ADDR = 28
    IPV6_NEXT_HOP = 62
    SOURCE_IPV4_PREFIX_LENGTH = 26
    DESTINATION_IPV4_PREFIX_LENGTH = 27
    SOURCE_IPV6_PREFIX_LENGTH = 61
    DESTINATION_IPV6_PREFIX_LENGTH = 62
    MPLS_TOP_LABEL_TYPE = 46
    MPLS_TOP_LABEL_IPV4_ADDRESS = 47
    MPLS_LABEL_STACK_SECTION_2 = 48
    MPLS_LABEL_STACK_SECTION_3 = 49
    MPLS_LABEL_STACK_SECTION_4 = 50
    MPLS_LABEL_STACK_SECTION_5 = 51
    MPLS_LABEL_STACK_SECTION_6 = 52
    MPLS_LABEL_STACK_SECTION_7 = 53
    MPLS_LABEL_STACK_SECTION_8 = 54
    MPLS_LABEL_STACK_SECTION_9 = 55
    MPLS_LABEL_STACK_SECTION_10 = 56
    VLAN_ID = 58
    POST_VLAN_ID = 59
    VLAN_PRIORITY = 60
    ICMP_TYPE_CODE_IPV4 = 176
    ICMP_TYPE_CODE_IPV6 = 177
    UDP_SOURCE_PORT = 7
    UDP_DESTINATION_PORT = 11
    TCP_SOURCE_PORT = 7
    TCP_DESTINATION_PORT = 11
    TCP_SEQUENCE_NUMBER = 184
    TCP_ACKNOWLEDGEMENT_NUMBER = 185
    TCP_WINDOW_SIZE = 186
    TCP_URGENT_POINTER = 187
    TCP_HEADER_LENGTH = 188
    IP_DIFFSERV_CODE_POINT = 198
    IP_PRECEDENCE = 199
    FRAGMENT_FLAGS = 194
    FRAGMENT_OFFSET = 195
    IP_TTL = 164
    NEXT_HOP_IPV6_ADDRESS = 62
    BGP_SOURCE_AS_NUMBER = 16
    BGP_DESTINATION_AS_NUMBER = 17
    BGP_NEXT_HOP_IPV4_ADDRESS = 18
    BGP_NEXT_HOP_IPV6_ADDRESS = 63
    FLOW_DIRECTION = 61
    IP_VERSION = 60
    FLOW_SAMPLER_ID = 48
    FLOW_SAMPLER_MODE = 49
    FLOW_SAMPLER_RANDOM_INTERVAL = 50
    SELECTOR_ID = 64
    SELECTOR_ALGORITHM = 65
    SAMPLING_PACKET_INTERVAL = 66
    SAMPLING_PACKET_SPACE = 67
    SAMPLING_TIME_INTERVAL = 68
    SAMPLING_TIME_SPACE = 69
    SAMPLING_SIZE = 70
    SAMPLING_POPULATION = 71
    SAMPLING_PROBABILITY = 72


@dataclass
class TemplateField:
    """Single field in a template."""
    field_id: int
    field_length: int
    enterprise_id: int = 0  # For IPFIX enterprise-specific fields


@dataclass
class Template:
    """Template definition for flow records."""
    template_id: int
    field_count: int
    fields: list[TemplateField] = field(default_factory=list)
    scope_field_count: int = 0  # For IPFIX options templates
    scope_fields: list[TemplateField] = field(default_factory=list)
    
    def get_format_string(self) -> str:
        """Generate struct format string for this template."""
        fmt = "!"  # Network byte order
        for f in self.fields:
            if f.field_length == 1:
                fmt += "B"
            elif f.field_length == 2:
                fmt += "H"
            elif f.field_length == 4:
                fmt += "I"
            elif f.field_length == 8:
                fmt += "Q"
            elif f.field_length == 16:
                fmt += "16s"
            else:
                fmt += f"{f.field_length}s"
        return fmt
    
    def get_field_names(self) -> list[str]:
        """Get human-readable field names."""
        names = []
        for f in self.fields:
            names.append(self._field_id_to_name(f.field_id, f.enterprise_id))
        return names
    
    def _field_id_to_name(self, field_id: int, enterprise_id: int = 0) -> str:
        """Convert field ID to human-readable name."""
        field_names = {
            FieldType.IN_BYTES: "bytes",
            FieldType.IN_PACKETS: "packets",
            FieldType.FLOWS: "flows",
            FieldType.IN_PROTOCOL: "protocol",
            FieldType.IPV4_SRC_ADDR: "src_ip",
            FieldType.IPV4_DST_ADDR: "dst_ip",
            FieldType.IPV4_NEXT_HOP: "next_hop",
            FieldType.INPUT_SNMP: "input_iface",
            FieldType.OUTPUT_SNMP: "output_iface",
            FieldType.L4_SRC_PORT: "src_port",
            FieldType.L4_DST_PORT: "dst_port",
            FieldType.TCP_FLAGS: "tcp_flags",
            FieldType.IP_TOS: "tos",
            FieldType.SRC_AS: "src_as",
            FieldType.DST_AS: "dst_as",
            FieldType.SRC_MASK: "src_mask",
            FieldType.DST_MASK: "dst_mask",
            FieldType.FIRST_SWITCHED: "start_time",
            FieldType.LAST_SWITCHED: "end_time",
            FieldType.IPV6_SRC_ADDR: "src_ip",
            FieldType.IPV6_DST_ADDR: "dst_ip",
            FieldType.OCTET_DELTA_COUNT: "bytes",
            FieldType.PACKET_DELTA_COUNT: "packets",
            FieldType.FLOW_START_MILLISECONDS: "start_time",
            FieldType.FLOW_END_MILLISECONDS: "end_time",
            FieldType.FLOW_START_MICROSECONDS: "start_time",
            FieldType.FLOW_END_MICROSECONDS: "end_time",
            FieldType.FLOW_START_NANOSECONDS: "start_time",
            FieldType.FLOW_END_NANOSECONDS: "end_time",
            FieldType.BIFLOW_DIRECTION: "biflow_direction",
            FieldType.SOURCE_IPV4_PREFIX_LENGTH: "src_mask",
            FieldType.DESTINATION_IPV4_PREFIX_LENGTH: "dst_mask",
            FieldType.SOURCE_IPV6_PREFIX_LENGTH: "src_mask",
            FieldType.DESTINATION_IPV6_PREFIX_LENGTH: "dst_mask",
            FieldType.VLAN_ID: "vlan_id",
            FieldType.ICMP_TYPE_CODE_IPV4: "icmp_type_code",
            FieldType.ICMP_TYPE_CODE_IPV6: "icmp_type_code",
            FieldType.TCP_SEQUENCE_NUMBER: "tcp_seq",
            FieldType.TCP_ACKNOWLEDGEMENT_NUMBER: "tcp_ack",
            FieldType.TCP_WINDOW_SIZE: "tcp_window",
            FieldType.TCP_URGENT_POINTER: "tcp_urgent",
            FieldType.TCP_HEADER_LENGTH: "tcp_header_len",
            FieldType.IP_DIFFSERV_CODE_POINT: "dscp",
            FieldType.IP_PRECEDENCE: "ip_precedence",
            FieldType.FRAGMENT_FLAGS: "fragment_flags",
            FieldType.FRAGMENT_OFFSET: "fragment_offset",
            FieldType.IP_TTL: "ttl",
            FieldType.BGP_SOURCE_AS_NUMBER: "src_as",
            FieldType.BGP_DESTINATION_AS_NUMBER: "dst_as",
            FieldType.BGP_NEXT_HOP_IPV4_ADDRESS: "bgp_next_hop_v4",
            FieldType.BGP_NEXT_HOP_IPV6_ADDRESS: "bgp_next_hop_v6",
            FieldType.FLOW_DIRECTION: "flow_direction",
            FieldType.IP_VERSION: "ip_version",
            FieldType.FLOW_SAMPLER_ID: "sampler_id",
        }
        if enterprise_id == 0:
            return field_names.get(field_id, f"field_{field_id}")
        else:
            return f"enterprise_{enterprise_id}_field_{field_id}"


class TemplateCache:
    """Cache for storing templates by (source_ip, template_id)."""
    
    def __init__(self):
        self._templates: dict[tuple[str, int], Template] = {}
    
    def add(self, source_ip: str, template: Template):
        """Add a template to cache."""
        key = (source_ip, template.template_id)
        self._templates[key] = template
        logger.debug("template_cached", source_ip=source_ip, template_id=template.template_id, field_count=template.field_count)
    
    def get(self, source_ip: str, template_id: int) -> Template | None:
        """Get a template from cache."""
        key = (source_ip, template_id)
        return self._templates.get(key)
    
    def remove(self, source_ip: str, template_id: int):
        """Remove a template from cache."""
        key = (source_ip, template_id)
        self._templates.pop(key, None)
    
    def clear(self, source_ip: str | None = None):
        """Clear templates for a source or all."""
        if source_ip:
            keys_to_remove = [k for k in self._templates if k[0] == source_ip]
            for k in keys_to_remove:
                del self._templates[k]
        else:
            self._templates.clear()


# Global template cache
template_cache = TemplateCache()


class NetFlowV9IPFIXParser:
    """Parser for NetFlow v9 and IPFIX packets."""
    
    # NetFlow v9 header: version(2) count(2) sys_uptime(4) unix_secs(4) 
    # package_sequence(4) source_id(4)
    NETFLOW_V9_HEADER_FORMAT = "!HHIIII"
    NETFLOW_V9_HEADER_SIZE = struct.calcsize(NETFLOW_V9_HEADER_FORMAT)
    
    # IPFIX header: version(2) length(2) export_time(4) sequence(4) observation_domain_id(4)
    IPFIX_HEADER_FORMAT = "!HHIIII"
    IPFIX_HEADER_SIZE = struct.calcsize(IPFIX_HEADER_FORMAT)
    
    # FlowSet header: flowset_id(2) length(2)
    FLOWSET_HEADER_FORMAT = "!HH"
    FLOWSET_HEADER_SIZE = struct.calcsize(FLOWSET_HEADER_FORMAT)
    
    # Template FlowSet: flowset_id=0 (template) or 1 (options template)
    TEMPLATE_FLOWSET_ID = 0
    OPTIONS_TEMPLATE_FLOWSET_ID = 1
    DATA_FLOWSET_ID_BASE = 256  # Template IDs >= 256 are data flowsets
    
    def __init__(self):
        self.protocol = "unknown"
    
    def can_handle(self, data: bytes) -> bool:
        """Check if this is NetFlow v9 or IPFIX."""
        if len(data) < 2:
            return False
        version = struct.unpack("!H", data[:2])[0]
        return version in (9, 10)  # v9 = 9, IPFIX = 10
    
    def parse(self, data: bytes, source_ip: str, source_port: int) -> list[dict[str, Any]]:
        """Parse NetFlow v9 or IPFIX packet."""
        if len(data) < 2:
            return []
        
        version = struct.unpack("!H", data[:2])[0]
        
        if version == 9:
            self.protocol = "netflow_v9"
            return self._parse_netflow_v9(data, source_ip, source_port)
        elif version == 10:
            self.protocol = "ipfix"
            return self._parse_ipfix(data, source_ip, source_port)
        
        return []
    
    def _parse_netflow_v9(self, data: bytes, source_ip: str, source_port: int) -> list[dict[str, Any]]:
        """Parse NetFlow v9 packet."""
        if len(data) < self.NETFLOW_V9_HEADER_SIZE:
            logger.warning("netflow_v9_packet_too_short", length=len(data))
            return []
        
        try:
            header = struct.unpack(self.NETFLOW_V9_HEADER_FORMAT, data[:self.NETFLOW_V9_HEADER_SIZE])
        except struct.error as e:
            logger.warning("netflow_v9_header_unpack_failed", error=str(e))
            return []
        
        version, count, sys_uptime, unix_secs, package_sequence, source_id = header
        
        if version != 9:
            logger.warning("netflow_v9_wrong_version", version=version)
            return []
        
        flows = []
        offset = self.NETFLOW_V9_HEADER_SIZE
        
        for _ in range(count):
            if offset + self.FLOWSET_HEADER_SIZE > len(data):
                logger.warning("netflow_v9_truncated_flowset_header")
                break
            
            flowset_id, flowset_length = struct.unpack(
                self.FLOWSET_HEADER_FORMAT, data[offset:offset + self.FLOWSET_HEADER_SIZE]
            )
            offset += self.FLOWSET_HEADER_SIZE
            
            flowset_data = data[offset:offset + flowset_length - self.FLOWSET_HEADER_SIZE]
            offset += flowset_length - self.FLOWSET_HEADER_SIZE
            
            # Align to 4-byte boundary
            offset = (offset + 3) & ~3
            
            if flowset_id == self.TEMPLATE_FLOWSET_ID:
                self._parse_template_flowset(flowset_data, source_ip)
            elif flowset_id == self.OPTIONS_TEMPLATE_FLOWSET_ID:
                self._parse_options_template_flowset(flowset_data, source_ip)
            elif flowset_id >= self.DATA_FLOWSET_ID_BASE:
                flows.extend(self._parse_data_flowset(flowset_data, source_ip, flowset_id, sys_uptime, unix_secs, package_sequence, source_id))
        
        logger.debug("netflow_v9_parsed", source_ip=source_ip, flow_count=len(flows), sequence=package_sequence)
        return flows
    
    def _parse_ipfix(self, data: bytes, source_ip: str, source_port: int) -> list[dict[str, Any]]:
        """Parse IPFIX packet."""
        if len(data) < self.IPFIX_HEADER_SIZE:
            logger.warning("ipfix_packet_too_short", length=len(data))
            return []
        
        try:
            header = struct.unpack(self.IPFIX_HEADER_FORMAT, data[:self.IPFIX_HEADER_SIZE])
        except struct.error as e:
            logger.warning("ipfix_header_unpack_failed", error=str(e))
            return []
        
        version, length, export_time, sequence, observation_domain_id = header
        
        if version != 10:
            logger.warning("ipfix_wrong_version", version=version)
            return []
        
        if length != len(data):
            logger.warning("ipfix_length_mismatch", expected=length, actual=len(data))
        
        flows = []
        offset = self.IPFIX_HEADER_SIZE
        
        while offset + self.FLOWSET_HEADER_SIZE <= len(data):
            flowset_id, flowset_length = struct.unpack(
                self.FLOWSET_HEADER_FORMAT, data[offset:offset + self.FLOWSET_HEADER_SIZE]
            )
            offset += self.FLOWSET_HEADER_SIZE
            
            if flowset_length < self.FLOWSET_HEADER_SIZE:
                logger.warning("ipfix_invalid_flowset_length", length=flowset_length)
                break
            
            flowset_data_len = flowset_length - self.FLOWSET_HEADER_SIZE
            if offset + flowset_data_len > len(data):
                logger.warning("ipfix_truncated_flowset")
                break
            
            flowset_data = data[offset:offset + flowset_data_len]
            offset += flowset_data_len
            
            # Align to 4-byte boundary
            offset = (offset + 3) & ~3
            
            if flowset_id == self.TEMPLATE_FLOWSET_ID:
                self._parse_template_flowset(flowset_data, source_ip)
            elif flowset_id == self.OPTIONS_TEMPLATE_FLOWSET_ID:
                self._parse_options_template_flowset(flowset_data, source_ip)
            elif flowset_id >= self.DATA_FLOWSET_ID_BASE:
                flows.extend(self._parse_data_flowset(flowset_data, source_ip, flowset_id, 0, export_time, sequence, observation_domain_id))
        
        logger.debug("ipfix_parsed", source_ip=source_ip, flow_count=len(flows), sequence=sequence)
        return flows
    
    def _parse_template_flowset(self, data: bytes, source_ip: str):
        """Parse a template flowset (v9 or IPFIX)."""
        offset = 0
        while offset + 4 <= len(data):  # template_id(2) + field_count(2)
            template_id, field_count = struct.unpack("!HH", data[offset:offset + 4])
            offset += 4
            
            template = Template(template_id=template_id, field_count=field_count)
            
            for _ in range(field_count):
                if offset + 4 > len(data):
                    logger.warning("netflow_v9_truncated_template_field")
                    break
                field_id, field_length = struct.unpack("!HH", data[offset:offset + 4])
                offset += 4
                
                template.fields.append(TemplateField(field_id=field_id, field_length=field_length))
            
            template_cache.add(source_ip, template)
    
    def _parse_options_template_flowset(self, data: bytes, source_ip: str):
        """Parse an options template flowset (IPFIX)."""
        offset = 0
        while offset + 6 <= len(data):  # template_id(2) + scope_field_count(2) + field_count(2)
            template_id, scope_field_count, field_count = struct.unpack("!HHH", data[offset:offset + 6])
            offset += 6
            
            template = Template(
                template_id=template_id,
                field_count=field_count,
                scope_field_count=scope_field_count
            )
            
            # Parse scope fields
            for _ in range(scope_field_count):
                if offset + 4 > len(data):
                    break
                field_id, field_length = struct.unpack("!HH", data[offset:offset + 4])
                offset += 4
                template.scope_fields.append(TemplateField(field_id=field_id, field_length=field_length))
            
            # Parse option fields
            for _ in range(field_count):
                if offset + 4 > len(data):
                    break
                field_id, field_length = struct.unpack("!HH", data[offset:offset + 4])
                offset += 4
                template.fields.append(TemplateField(field_id=field_id, field_length=field_length))
            
            template_cache.add(source_ip, template)
    
    def _parse_data_flowset(
        self,
        data: bytes,
        source_ip: str,
        template_id: int,
        sys_uptime: int,
        unix_secs: int,
        package_sequence: int,
        source_id: int
    ) -> list[dict[str, Any]]:
        """Parse a data flowset using cached template."""
        template = template_cache.get(source_ip, template_id)
        if not template:
            logger.warning("template_not_found", source_ip=source_ip, template_id=template_id)
            return []
        
        fmt = template.get_format_string()
        record_size = struct.calcsize(fmt)
        field_names = template.get_field_names()
        
        flows = []
        offset = 0
        
        while offset + record_size <= len(data):
            try:
                record = struct.unpack(fmt, data[offset:offset + record_size])
            except struct.error as e:
                logger.warning("data_flowset_unpack_failed", error=str(e), offset=offset)
                break
            
            flow = {
                "version": 9 if self.protocol == "netflow_v9" else 10,
                "source_ip": source_ip,
                "template_id": template_id,
                "sys_uptime": sys_uptime,
                "unix_secs": unix_secs,
                "package_sequence": package_sequence,
                "source_id": source_id,
            }
            
            for i, (name, value) in enumerate(zip(field_names, record)):
                # Convert IP addresses
                if name in ("src_ip", "dst_ip", "next_hop", "bgp_next_hop_v4") and isinstance(value, (bytes, int)):
                    if isinstance(value, int):
                        flow[name] = struct.unpack("!I", struct.pack("!I", value))[0]
                    if isinstance(value, bytes) and len(value) == 4:
                        import socket
                        flow[name] = socket.inet_ntoa(value)
                    elif isinstance(value, bytes) and len(value) == 16:
                        import socket
                        flow[name] = socket.inet_ntop(socket.AF_INET6, value)
                elif name in ("start_time", "end_time") and isinstance(value, int):
                    # Convert to seconds if milliseconds/microseconds/nanoseconds
                    flow[name] = value
                else:
                    flow[name] = value
            
            flows.append(flow)
            offset += record_size
        
        return flows


def parse_netflow_v9(data: bytes, source_ip: str = "", source_port: int = 0) -> list[dict[str, Any]]:
    """Convenience function to parse NetFlow v9."""
    parser = NetFlowV9IPFIXParser()
    return parser.parse(data, source_ip, source_port)


def parse_ipfix(data: bytes, source_ip: str = "", source_port: int = 0) -> list[dict[str, Any]]:
    """Convenience function to parse IPFIX."""
    parser = NetFlowV9IPFIXParser()
    return parser.parse(data, source_ip, source_port)