"""
FlowSight Collector - Main Entry Point

UDP server for receiving NetFlow/sFlow/IPFIX packets.
"""

import asyncio
import signal
import sys
from contextlib import asynccontextmanager

import click
from rich.console import Console

from flowsight import setup_logging, get_logger, settings
from flowsight.collector.server import FlowCollector

console = Console()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(collector: FlowCollector):
    """Application lifespan manager."""
    logger.info("starting_flow_collector", listen=settings.collector.listen)
    await collector.start()
    try:
        yield
    finally:
        logger.info("stopping_flow_collector")
        await collector.stop()


async def run_collector():
    """Run the flow collector."""
    setup_logging()
    
    collector = FlowCollector(
        host=settings.collector.listen.split(":")[0],
        port=int(settings.collector.listen.split(":")[1]),
        protocols=settings.collector.protocols,
        workers=settings.collector.workers,
    )
    
    # Handle shutdown signals
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(collector.stop()))
    
    async with lifespan(collector):
        # Keep running
        await collector.wait_closed()


@click.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=str),
    help="Path to config.yaml file",
)
@click.option(
    "--listen",
    "-l",
    help="Listen address (host:port)",
)
@click.option(
    "--workers",
    "-w",
    type=int,
    help="Number of worker processes",
)
@click.option(
    "--debug/--no-debug",
    default=False,
    help="Enable debug logging",
)
def main(config: str | None, listen: str | None, workers: int | None, debug: bool):
    """FlowSight Flow Collector - Receive NetFlow/sFlow/IPFIX packets."""
    
    # Override settings from CLI
    if config:
        from flowsight.config import load_config
        load_config(config)
    
    if listen:
        settings.collector.listen = listen
    if workers:
        settings.collector.workers = workers
    if debug:
        settings.logging.level = "DEBUG"
    
    console.print(f"[bold cyan]FlowSight Collector v{__import__('flowsight').__version__}[/bold cyan]")
    console.print(f"Listening on: {settings.collector.listen}")
    console.print(f"Protocols: {', '.join(settings.collector.protocols)}")
    console.print(f"Workers: {settings.collector.workers}")
    
    try:
        asyncio.run(run_collector())
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
    except Exception as e:
        logger.exception("collector_failed", error=str(e))
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()