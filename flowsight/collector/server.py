"""
FlowSight Collector - UDP Server

Asyncio-based UDP server for receiving flow packets.
"""

import asyncio
import struct
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from flowsight import get_logger
from flowsight.parser.netflow_v5 import NetFlowV5Parser
from flowsight.parser.netflow_v9 import NetFlowV9IPFIXParser
from flowsight.parser.sflow import SFlowParser

logger = get_logger(__name__)

NETFLOW_V5_VERSION = 5


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
    """NetFlow v5 packet handler.

    Delegates parsing to :class:`flowsight.parser.netflow_v5.NetFlowV5Parser`
    and annotates each flow with the exporter address.
    """

    def __init__(self):
        self._parser = NetFlowV5Parser()

    def can_handle(self, data: bytes) -> bool:
        if len(data) < self._parser.HEADER_SIZE:
            return False
        version, _count = struct.unpack("!HH", data[:4])
        return version == NETFLOW_V5_VERSION

    def parse(self, data: bytes, source_ip: str, source_port: int) -> list[dict[str, Any]]:
        flows = self._parser.parse(data)
        for flow in flows:
            flow["source_ip"] = source_ip
            flow["source_port"] = source_port
        return flows


class NetFlowV9IPFIXHandler(FlowProtocolHandler):
    """NetFlow v9 / IPFIX packet handler using template cache."""

    def __init__(self):
        self._parser = NetFlowV9IPFIXParser()

    def can_handle(self, data: bytes) -> bool:
        return self._parser.can_handle(data)

    def parse(self, data: bytes, source_ip: str, source_port: int) -> list[dict[str, Any]]:
        return self._parser.parse(data, source_ip, source_port)


class SFlowHandler(FlowProtocolHandler):
    """sFlow packet handler."""

    def __init__(self):
        self._parser = SFlowParser()

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
        pipeline: Any | None = None,
    ):
        self.host = host
        self.port = port
        self.protocols = protocols or ["netflow_v5", "netflow_v9", "ipfix", "sflow"]
        self.workers = workers
        self.pipeline = pipeline
        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: FlowCollectorProtocol | None = None
        self._handlers: dict[str, FlowProtocolHandler] = {}
        self._queue: asyncio.Queue[FlowPacket] = asyncio.Queue(maxsize=10000)
        self._worker_tasks: list[asyncio.Task] = []
        self._running = False
        self._closed = asyncio.Event()
        self._closed.set()  # not running yet: wait_closed returns immediately
        self._init_handlers()

    def _init_handlers(self):
        """Initialize protocol handlers."""
        self._handlers["netflow_v5"] = NetFlowV5Handler()
        self._handlers["netflow_v9"] = NetFlowV9IPFIXHandler()
        self._handlers["ipfix"] = NetFlowV9IPFIXHandler()
        self._handlers["sflow"] = SFlowHandler()

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
        self._closed.clear()
        logger.info("collector_started", host=self.host, port=self.port)

        # Start worker tasks
        self._worker_tasks = [
            asyncio.create_task(self._worker(f"worker-{i}")) for i in range(self.workers)
        ]

    async def stop(self, timeout: float = 5.0):
        """Stop the collector.

        Closes the transport, waits up to ``timeout`` for workers to
        finish in-flight packets, and logs how many queued packets were
        dropped. Never blocks indefinitely.
        """
        if not self._running:
            return

        self._running = False
        if self._transport:
            self._transport.close()

        if self._worker_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._worker_tasks, return_exceptions=True), timeout=timeout
                )
            except TimeoutError:
                logger.warning("collector_workers_stop_timeout", workers=len(self._worker_tasks))
                for task in self._worker_tasks:
                    task.cancel()
                await asyncio.gather(*self._worker_tasks, return_exceptions=True)

        dropped = self._queue.qsize()
        if dropped:
            logger.warning("collector_queue_dropped_on_shutdown", dropped=dropped)

        self._closed.set()
        logger.info("collector_stopped")

    async def wait_closed(self):
        """Wait until collector is closed."""
        await self._closed.wait()

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
        """Process a parsed flow packet through the pipeline."""
        if self.pipeline is not None and packet.parsed_flows:
            await self.pipeline.process_flows(packet.parsed_flows)
        logger.debug(
            "packet_processed",
            source_ip=packet.source_ip,
            protocol=packet.protocol,
            flow_count=len(packet.parsed_flows),
        )


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
                            timestamp=time.monotonic(),
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
