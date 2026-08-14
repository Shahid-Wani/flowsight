"""
Tests for FlowSight NetFlow v5 and NetFlow v9/IPFIX parsers.
"""

import socket
import struct

from flowsight.parser.netflow_v5 import NetFlowV5Parser, parse_netflow_v5
from flowsight.parser.netflow_v9 import NetFlowV9IPFIXParser, parse_netflow_v9, parse_ipfix


class TestNetFlowV5Parser:
    """Test NetFlow v5 parsing."""

    def test_parse_empty_data(self):
        """Test parsing empty data returns empty list."""
        parser = NetFlowV5Parser()
        result = parser.parse(b"")
        assert result == []

    def test_parse_short_data(self):
        """Test parsing data shorter than header."""
        parser = NetFlowV5Parser()
        result = parser.parse(b"123")
        assert result == []

    def test_parse_wrong_version(self):
        """Test parsing non-v5 data returns empty list."""
        # Version 9 in header
        data = b"\x00\x09" + b"\x00" * 22  # version=9, rest zeros
        parser = NetFlowV5Parser()
        result = parser.parse(data)
        assert result == []

    def test_parse_valid_v5_packet(self):
        """Test parsing a valid NetFlow v5 packet with one flow."""
        # Build header: version=5, count=1, sys_uptime=1000, unix_secs=1600000000,
        # unix_nsecs=0, flow_sequence=0, engine_type=0, engine_id=0, sampling_interval=0
        header = struct.pack("!HHIIIIBBH", 5, 1, 1000, 1600000000, 0, 0, 0, 0, 0)

        # Build flow record - NetFlow v5 format (48 bytes)
        # src_addr(4) dst_addr(4) next_hop(4) input_iface(2) output_iface(2)
        # packet_count(4) byte_count(4) start_time(4) end_time(4)
        # src_port(2) dst_port(2) pad1(1) tcp_flags(1) proto(1) tos(1)
        # src_as(2) dst_as(2) src_mask(1) dst_mask(1) pad2(2)
        src_ip = socket.inet_aton("192.168.1.1")
        dst_ip = socket.inet_aton("10.0.0.1")
        next_hop = socket.inet_aton("192.168.1.254")

        flow = struct.pack(
            "!IIIHHIIIIHHBBBBHHBBH",
            int.from_bytes(src_ip, "big"),
            int.from_bytes(dst_ip, "big"),
            int.from_bytes(next_hop, "big"),
            1,  # input_iface
            2,  # output_iface
            100,  # packet_count
            10000,  # byte_count
            100,  # start_time
            200,  # end_time
            12345,  # src_port
            80,  # dst_port
            0,  # pad1
            0x10,  # tcp_flags (ACK)
            6,  # protocol (TCP)
            0,  # tos
            100,  # src_as
            200,  # dst_as
            24,  # src_mask
            24,  # dst_mask
            0,  # pad2
        )

        data = header + flow
        parser = NetFlowV5Parser()
        result = parser.parse(data)

        assert len(result) == 1
        flow_data = result[0]
        assert flow_data["version"] == 5
        assert flow_data["src_ip"] == "192.168.1.1"
        assert flow_data["dst_ip"] == "10.0.0.1"
        assert flow_data["next_hop"] == "192.168.1.254"
        assert flow_data["packet_count"] == 100
        assert flow_data["byte_count"] == 10000
        assert flow_data["src_port"] == 12345
        assert flow_data["dst_port"] == 80
        assert flow_data["protocol"] == 6
        assert flow_data["tcp_flags"] == 0x10

    def test_parse_multiple_flows(self):
        """Test parsing packet with multiple flows."""
        header = struct.pack("!HHIIIIBBH", 5, 2, 1000, 1600000000, 0, 0, 0, 0, 0)

        flows = []
        for i in range(2):
            src_ip = socket.inet_aton(f"192.168.1.{i+1}")
            dst_ip = socket.inet_aton(f"10.0.0.{i+1}")
            next_hop = socket.inet_aton("192.168.1.254")

            flow = struct.pack(
                "!IIIHHIIIIHHBBBBHHBBH",
                int.from_bytes(src_ip, "big"),
                int.from_bytes(dst_ip, "big"),
                int.from_bytes(next_hop, "big"),
                1, 2, 100, 10000, 100, 200, 12345, 80, 0, 0x10, 6, 0, 100, 200, 24, 24, 0
            )
            flows.append(flow)

        data = header + b"".join(flows)
        parser = NetFlowV5Parser()
        result = parser.parse(data)

        assert len(result) == 2
        assert result[0]["src_ip"] == "192.168.1.1"
        assert result[1]["src_ip"] == "192.168.1.2"

    def test_convenience_function(self):
        """Test parse_netflow_v5 convenience function."""
        header = struct.pack("!HHIIIIBBH", 5, 1, 1000, 1600000000, 0, 0, 0, 0, 0)
        src_ip = socket.inet_aton("192.168.1.1")
        dst_ip = socket.inet_aton("10.0.0.1")
        next_hop = socket.inet_aton("192.168.1.254")

        flow = struct.pack(
            "!IIIHHIIIIHHBBBBHHBBH",
            int.from_bytes(src_ip, "big"),
            int.from_bytes(dst_ip, "big"),
            int.from_bytes(next_hop, "big"),
            1, 2, 100, 10000, 100, 200, 12345, 80, 0, 0x10, 6, 0, 100, 200, 24, 24, 0
        )

        data = header + flow
        result = parse_netflow_v5(data)

        assert len(result) == 1
        assert result[0]["src_ip"] == "192.168.1.1"


class TestNetFlowV9IPFIXParser:
    """Test NetFlow v9 / IPFIX parsing."""

    def test_parse_empty_data(self):
        """Test parsing empty data returns empty list."""
        parser = NetFlowV9IPFIXParser()
        result = parser.parse(b"", "192.168.1.1", 2055)
        assert result == []

    def test_parse_short_data(self):
        """Test parsing data shorter than header."""
        parser = NetFlowV9IPFIXParser()
        result = parser.parse(b"123", "192.168.1.1", 2055)
        assert result == []

    def test_can_handle_v9(self):
        """Test can_handle for NetFlow v9."""
        parser = NetFlowV9IPFIXParser()
        # Version 9
        data = b"\x00\x09" + b"\x00" * 20
        assert parser.can_handle(data) is True

    def test_can_handle_ipfix(self):
        """Test can_handle for IPFIX."""
        parser = NetFlowV9IPFIXParser()
        # Version 10
        data = b"\x00\x0a" + b"\x00" * 20
        assert parser.can_handle(data) is True

    def test_can_handle_v5(self):
        """Test can_handle rejects NetFlow v5."""
        parser = NetFlowV9IPFIXParser()
        # Version 5
        data = b"\x00\x05" + b"\x00" * 20
        assert parser.can_handle(data) is False

    def test_parse_v9_without_template(self):
        """Test parsing v9 data without template returns empty."""
        # Minimal v9 packet with 0 flowsets
        header = struct.pack("!HHIIII", 9, 0, 1000, 1600000000, 0, 0)
        parser = NetFlowV9IPFIXParser()
        result = parser.parse(header, "192.168.1.1", 2055)
        assert result == []

    def test_parse_v9_with_data_no_template(self):
        """Test parsing v9 data flowset without template returns empty."""
        # v9 header with 1 flowset
        header = struct.pack("!HHIIII", 9, 1, 1000, 1600000000, 0, 0)
        # Data flowset (id=256) with 1 record but no template
        flowset_header = struct.pack("!HH", 256, 8)  # id=256, length=8 (header only)
        data = header + flowset_header
        parser = NetFlowV9IPFIXParser()
        result = parser.parse(data, "192.168.1.1", 2055)
        assert result == []


class TestConfig:
    """Test configuration loading."""

    def test_settings_load(self):
        """Test settings can be instantiated."""
        from flowsight.config import Settings
        settings = Settings()
        assert settings.collector.listen == "0.0.0.0:2055"
        assert settings.storage.type == "influxdb"

    def test_collector_config(self):
        """Test collector config defaults."""
        from flowsight.config import CollectorConfig
        config = CollectorConfig()
        assert config.listen == "0.0.0.0:2055"
        assert "netflow_v5" in config.protocols

    def test_storage_config(self):
        """Test storage config defaults."""
        from flowsight.config import StorageConfig
        config = StorageConfig()
        assert config.type == "influxdb"
        assert config.url == "http://localhost:8086"


class TestLogging:
    """Test logging setup."""

    def test_get_logger(self):
        """Test logger creation."""
        from flowsight.logging import get_logger
        logger = get_logger("test")
        assert logger is not None

    def test_log_context(self):
        """Test log context manager."""
        from flowsight.logging import LogContext
        with LogContext(key="value"):
            pass  # Should not raise