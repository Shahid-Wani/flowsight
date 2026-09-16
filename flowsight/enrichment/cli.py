"""FlowSight Enrichment CLI - enrich flow records with GeoIP, ASN, and threat intel."""

import asyncio
import json
import sys
from pathlib import Path

import click
from rich.console import Console

from flowsight import get_logger, setup_logging

console = Console()
logger = get_logger(__name__)


async def run_enrichment(flows: list[dict]) -> list[dict]:
    """Enrich a batch of flow records and return the enriched records."""
    from flowsight.enrichment.manager import get_enrichment_manager

    manager = await get_enrichment_manager()
    try:
        return await manager.enrich_batch_async(flows)
    finally:
        await manager.close()


@click.command()
@click.option(
    "--config", "-c", type=click.Path(exists=True, path_type=str), help="Path to config.yaml file"
)
@click.option(
    "--input",
    "-i",
    "input_path",
    type=click.Path(exists=True, path_type=str),
    help="JSON file of flow records (e.g. demo-flows.json from scripts/generate_demo_data.py)",
)
@click.option("--flow", "flow_json", help="Single flow record as a JSON string")
@click.option(
    "--output", "-o", type=click.Path(path_type=str), help="Write enriched records to a JSON file"
)
@click.option("--debug/--no-debug", default=False, help="Enable debug logging")
def main(
    config: str | None,
    input_path: str | None,
    flow_json: str | None,
    output: str | None,
    debug: bool,
):
    """FlowSight Enrichment - Enrich flows with GeoIP, ASN, and threat intel."""

    if config:
        from flowsight.config import load_config

        load_config(config)

    if debug:
        from flowsight import settings

        settings.logging.level = "DEBUG"

    setup_logging()

    if input_path:
        flows = json.loads(Path(input_path).read_text(encoding="utf-8"))
    elif flow_json:
        flows = [json.loads(flow_json)]
    else:
        flows = json.load(sys.stdin)

    console.print("[bold cyan]FlowSight Enrichment[/bold cyan]")
    console.print(f"Enriching {len(flows)} flow record(s)...")

    try:
        enriched = asyncio.run(run_enrichment(flows))
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
        return
    except Exception as e:
        logger.exception("enrichment_cli_failed", error=str(e))
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    if output:
        Path(output).write_text(json.dumps(enriched, indent=2) + "\n", encoding="utf-8")
        console.print(f"Wrote {len(enriched)} enriched record(s) to {output}")
    else:
        console.print_json(json.dumps(enriched))


if __name__ == "__main__":
    main()
