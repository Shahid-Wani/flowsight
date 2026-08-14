"""
FlowSight Collector - UDP Server

Asyncio-based UDP server for receiving flow packets.
"""

import asyncio
import socket
import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from flowsight import get_logger
from flowsight.parser.netflow_v5 import parse_netflow_v5
from flowsight.parser.netflow_v9 import NetFlowV9IPFIXParser

logger = get_logger(__name__)


@dataclass
class FlowPacket:
    """Parsed flow packet with metadata."""

    data: bytes
    source_ip: str
    source_port: int
    protocol: str
    timestamp: float
    parsed_flows: list[dict[str, Any]]


class FlowProtocolHandler(ABC):
    """Base class for flow protocol handlers."""

    @abstractmethod
    def can_handle(self, data: bytes) -> bool:
        """Check if this handler can parse the data."""

    @abstractmethod
    def parse(self, data: bytes, source_ip: str, source_port: int) -> list[dict[str, Any]]:
        """Parse flow data and return list of flow records."""


class NetFlowV5Handler(FlowProtocolHandler):
    """NetFlow v5 packet handler."""

    # NetFlow v5 header format
    HEADER_FORMAT = "!HHIIIIHH"
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

    # NetFlow v5 flow record format
    FLOW_FORMAT = "!IIIIHHHHHHBBBBBBBBHBB"
    FLOW_SIZE = struct.calcsize(FLOW_FORMAT)

    def can_handle(self, data: bytes) -> bool:
        if len(data) < self.HEADER_SIZE:
            return False
        version, count = struct.unpack("!HH", data[:4])
        return version == 5

    def parse(self, data: bytes, source_ip: str, source_port: int) -> list[dict[str, Any]]:
        if len(data) < self.HEADER_SIZE:
            return []

        header = struct.unpack(self.HEADER_FORMAT, data[: self.HEADER_SIZE])
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

        flows = []
        offset = self.HEADER_SIZE

        for i in range(count):
            if offset + self.FLOW_SIZE > len(data):
                break

            flow_data = struct.unpack(self.FLOW_FORMAT, data[offset : offset + self.FLOW_SIZE])
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

            # Convert IPs
            src_ip = socket.inet_ntoa(struct.pack("!I", src_addr))
            dst_ip = socket.inet_ntoa(struct.pack("!I", dst_addr))
            next_hop_ip = socket.inet_ntoa(struct.pack("!I", next_hop))

            flow = {
                "version": 5,
                "source_ip": source_ip,
                "source_port": source_port,
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
            }
            flows.append(flow)

        return flows


class NetFlowV9IPFIXHandler(FlowProtocolHandler):
    """NetFlow v9 / IPFIX packet handler using template cache."""

    def __init__(self):
        self._parser = NetFlowV9IPFIXParser()

    def can_handle(self, data: bytes) -> bool:
        return self._parser.can_handle(data)

    def parse(self, data: bytes, source_ip: str, source_port: int) -> list[dict[str, Any]]:
        return self._parser.parse(data, source_ip, source_port)


class FlowCollector:
    """Asyncio UDP flow collector."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 2055,
        protocols: list[str] | None = None,
        workers: int = 4,
    ):
        self.host = host
        self.port = port
        self.protocols = protocols or ["netflow_v5", "netflow_v9", "ipfix", "sflow"]
        self.workers = workers
        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: "FlowCollectorProtocol | None" = None
        self._handlers: dict[str, FlowProtocolHandler] = {}
        self._queue: asyncio.Queue[FlowPacket] = asyncio.Queue(maxsize=10000)
        self._running = False
        self._init_handlers()

    def _init_handlers(self):
        """Initialize protocol handlers."""
        self._handlers["netflow_v5"] = NetFlowV5Handler()
        self._handlers["netflow_v9"] = NetFlowV9IPFIXHandler()
        self._handlers["ipfix"] = NetFlowV9IPFIXHandler()
        # sFlow handler will be added in Day 3

    async def start(self):
        """Start the collector."""
        if self._running:
            return

        loop = asyncio.get_running_loop()
        self._transport, self._protocol = await loop.create_datagram_endpoint(
            lambda: FlowCollectorProtocol(self._queue, self._handlers),
            local_addr=(self.host, self.port),
        )

        self._running = True
        logger.info("collector_started", host=self.host, port=self.port)

        # Start worker tasks
        for i in range(self.workers):
            asyncio.create_task(self._worker(f"worker-{i}"))

    async def stop(self):
        """Stop the collector."""
        if not self._running:
            return

        self._running = False
        if self._transport:
            self._transport.close()

        # Wait for queue to drain
        await self._queue.join()
        logger.info("collector_stopped")

    async def wait_closed(self):
        """Wait until collector is closed."""
        while self._running:
            await asyncio.sleep(1)

    async def _worker(self, name: str):
        """Worker task to process flow packets."""
        logger.debug("worker_started", worker=name)
        while self._running:
            try:
                packet = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._process_packet(packet)
                self._queue.task_done()
            except TimeoutError:
                continue
            except Exception as e:
                logger.exception("worker_error", worker=name, error=str(e))
        logger.debug("worker_stopped", worker=name)

    async def _process_packet(self, packet: FlowPacket):
        """Process a parsed flow packet."""
        # This will be connected to storage/enrichment/detection in later days
        logger.debug(
            "packet_received",
            source_ip=packet.source_ip,
            protocol=packet.protocol,
            flow_count=len(packet.parsed_flows),
        )
        # TODO: Send to storage pipeline


class FlowCollectorProtocol(asyncio.DatagramProtocol):
    """Asyncio protocol for receiving UDP packets."""

    def __init__(self, queue: asyncio.Queue, handlers: dict[str, FlowProtocolHandler]):
        self.queue = queue
        self.handlers = handlers

    def datagram_received(self, data: bytes, addr: tuple[str, int]):
        """Handle received UDP datagram."""
        source_ip, source_port = addr

        # Try each handler
        for protocol_name, handler in self.handlers.items():
            if handler.can_handle(data):
                try:
                    flows = handler.parse(data, source_ip, source_port)
                    if flows:
                        packet = FlowPacket(
                            data=data,
                            source_ip=source_ip,
                            source_port=source_port,
                            protocol=protocol_name,
                            timestamp=asyncio.get_event_loop().time(),
                            parsed_flows=flows,
                        )
                        # Non-blocking put
                        try:
                            self.queue.put_nowait(packet)
                        except asyncio.QueueFull:
                            logger.warning("queue_full_dropping_packet", source_ip=source_ip)
                except Exception as e:
                    logger.exception("parse_error", protocol=protocol_name, error=str(e))
                break