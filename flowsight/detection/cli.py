"""FlowSight Detection CLI - run anomaly detection on flow records."""

import asyncio
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from flowsight import get_logger, setup_logging
from flowsight.detection.ml import MIN_TRAINING_SAMPLES

console = Console()
logger = get_logger(__name__)


async def run_detection(flows: list[dict]) -> None:
    """Run statistical detection and threshold alerting over a batch of flows."""
    from flowsight import settings
    from flowsight.alerting.manager import get_alert_manager
    from flowsight.detection.statistical import StatisticalAnomalyDetector

    detector = StatisticalAnomalyDetector(
        z_threshold=settings.detection.statistical.zscore_threshold,
        min_samples=settings.detection.statistical.min_samples,
    )
    await detector.add_batch(flows)
    results = await detector.detect_batch(flows)

    table = Table(title="Anomaly Detection Results")
    table.add_column("Field")
    table.add_column("Value")
    table.add_column("Z-Score")
    table.add_column("Anomaly")

    anomalies = 0
    for batch in results:
        for result in batch:
            if result.is_anomaly:
                anomalies += 1
            table.add_row(
                result.field,
                f"{result.value:.0f}",
                f"{result.z_score:.2f}",
                "[red]YES[/red]" if result.is_anomaly else "no",
            )
    console.print(table)
    console.print(f"[yellow]Anomalies detected: {anomalies}[/yellow]")

    manager = await get_alert_manager()
    alerts = await manager.evaluate_batch(flows)
    console.print(f"[yellow]Alerts generated: {len(alerts)}[/yellow]")
    for alert in alerts:
        console.print(f"  [{alert.severity.value}] {alert.rule_name}: {alert.message}")


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
@click.option("--debug/--no-debug", default=False, help="Enable debug logging")
def main(config: str | None, input_path: str | None, debug: bool):
    """FlowSight Detection - Run threshold + statistical anomaly detection on flows."""

    if config:
        from flowsight.config import load_config

        load_config(config)

    if debug:
        from flowsight import settings

        settings.logging.level = "DEBUG"

    setup_logging()

    if input_path:
        flows = json.loads(Path(input_path).read_text(encoding="utf-8"))
    else:
        flows = json.load(sys.stdin)

    console.print("[bold cyan]FlowSight Detection[/bold cyan]")
    console.print(f"Analyzing {len(flows)} flow record(s)...")

    try:
        asyncio.run(run_detection(flows))
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
    except Exception as e:
        logger.exception("detection_cli_failed", error=str(e))
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@click.command()
@click.option(
    "--config", "-c", type=click.Path(exists=True, path_type=str), help="Path to config.yaml file"
)
@click.option(
    "--input",
    "-i",
    "input_path",
    type=click.Path(exists=True, path_type=str),
    help="JSON file of flow records to train on (e.g. demo-flows.json)",
)
@click.option("--debug/--no-debug", default=False, help="Enable debug logging")
def train(config: str | None, input_path: str | None, debug: bool):
    """FlowSight Train - train the ML anomaly model on flow records.

    The trained model is saved to ``detection.ml.model_path`` and picked
    up by the collector's pipeline at startup (online detection).
    """

    if config:
        from flowsight.config import load_config

        load_config(config)

    if debug:
        from flowsight import settings

        settings.logging.level = "DEBUG"

    setup_logging()

    if input_path:
        flows = json.loads(Path(input_path).read_text(encoding="utf-8"))
    else:
        flows = json.load(sys.stdin)

    console.print("[bold cyan]FlowSight Train[/bold cyan]")
    console.print(f"Training on {len(flows)} flow record(s)...")

    try:
        from flowsight import settings as current_settings
        from flowsight.detection.ml import MLAnomalyDetector

        detector = MLAnomalyDetector(model_path=current_settings.detection.ml.model_path)
        trained = asyncio.run(detector.train(flows))
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
        return
    except Exception as e:
        logger.exception("train_cli_failed", error=str(e))
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    if trained:
        console.print(
            f"[green]Model trained and saved to {current_settings.detection.ml.model_path}[/green]"
        )
        console.print(
            "The collector pipeline will load it at startup when detection.ml.enabled=true."
        )
    else:
        console.print(
            "[red]Training failed: not enough usable flow records "
            f"(need at least {MIN_TRAINING_SAMPLES} with all feature fields).[/red]"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
