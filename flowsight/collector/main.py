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

from flowsight import get_logger, settings, setup_logging
from flowsight.collector.server import FlowCollector
from flowsight.pipeline import Pipeline

console = Console()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(collector: FlowCollector, pipeline: Pipeline):
    """Application lifespan manager."""
    logger.info("starting_flow_collector", listen=settings.collector.listen)
    await collector.start()
    try:
        yield
    finally:
        logger.info("stopping_flow_collector")
        try:
            await asyncio.shield(collector.stop())
        except Exception as e:
            logger.warning("collector_stop_failed", error=str(e))
        try:
            await asyncio.shield(pipeline.stop())
        except Exception as e:
            logger.warning("pipeline_stop_failed", error=str(e))


async def run_collector():
    """Run the flow collector."""
    setup_logging()

    pipeline = await Pipeline.from_settings()
    collector = FlowCollector(
        host=settings.collector.listen.split(":")[0],
        port=int(settings.collector.listen.split(":")[1]),
        protocols=settings.collector.protocols,
        workers=settings.collector.workers,
        pipeline=pipeline,
    )

    # Handle shutdown signals (POSIX). On Windows add_signal_handler
    # raises NotImplementedError; shutdown falls back to the
    # KeyboardInterrupt path handled in main().
    loop = asyncio.get_running_loop()
    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, asyncio.create_task, collector.stop())
    except NotImplementedError:
        logger.debug("signal_handlers_unavailable_on_windows")

    async with lifespan(collector, pipeline):
        # Keep running
        await collector.wait_closed()


@click.command()
@click.option(
    "--config", "-c", type=click.Path(exists=True, path_type=str), help="Path to config.yaml file"
)
@click.option("--listen", "-l", help="Listen address (host:port)")
@click.option("--workers", "-w", type=int, help="Number of worker processes")
@click.option("--debug/--no-debug", default=False, help="Enable debug logging")
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

    console.print(
        f"[bold cyan]FlowSight Collector v{__import__('flowsight').__version__}[/bold cyan]"
    )
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
