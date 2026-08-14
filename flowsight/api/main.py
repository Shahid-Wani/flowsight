"""
FlowSight API - Main Entry Point

FastAPI REST API for flow data queries and real-time WebSocket updates.
"""

import asyncio
import sys
from contextlib import asynccontextmanager

import click
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from rich.console import Console

from flowsight import get_logger, settings, setup_logging
from flowsight.api.routes import router as api_router
from flowsight.api.websocket import router as ws_router
from flowsight.storage.influxdb import InfluxDBStorage

console = Console()
logger = get_logger(__name__)

# Global storage instance
storage: InfluxDBStorage | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global storage

    setup_logging()
    logger.info("starting_api_server", host=settings.api.host, port=settings.api.port)

    # Initialize storage
    storage = InfluxDBStorage()
    await storage.connect()

    # Store in app state
    app.state.storage = storage

    try:
        yield
    finally:
        logger.info("stopping_api_server")
        if storage:
            await storage.disconnect()


def create_app() -> FastAPI:
    """Create FastAPI application."""
    app = FastAPI(
        title="FlowSight API",
        description="NetFlow/sFlow/IPFIX Analyzer REST API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(ws_router, prefix="/api/v1")

    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "service": "flowsight-api"}

    return app


app = create_app()


async def run_server():
    """Run the API server."""
    import uvicorn

    config = uvicorn.Config(
        app,
        host=settings.api.host,
        port=settings.api.port,
        log_level=settings.logging.level.lower(),
        access_log=True,
    )
    server = uvicorn.Server(config)
    await server.serve()


@click.command()
@click.option(
    "--config", "-c", type=click.Path(exists=True, path_type=str), help="Path to config.yaml file"
)
@click.option("--host", "-h", help="Host to bind to")
@click.option("--port", "-p", type=int, help="Port to bind to")
@click.option("--debug/--no-debug", default=False, help="Enable debug logging")
def main(config: str | None, host: str | None, port: int | None, debug: bool):
    """FlowSight API Server - REST API for flow data."""

    # Override settings from CLI
    if config:
        from flowsight.config import load_config

        load_config(config)

    if host:
        settings.api.host = host
    if port:
        settings.api.port = port
    if debug:
        settings.logging.level = "DEBUG"

    console.print(f"[bold cyan]FlowSight API v{__import__('flowsight').__version__}[/bold cyan]")
    console.print(f"Host: {settings.api.host}")
    console.print(f"Port: {settings.api.port}")

    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
    except Exception as e:
        logger.exception("api_server_failed", error=str(e))
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
