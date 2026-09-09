#!/usr/bin/env python3
"""Generate deterministic sample flow records for local development."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from flowsight.demo import generate_flows


def main() -> None:
    """Write sample flows as a JSON array."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=20, help="number of records to generate")
    parser.add_argument("--seed", type=int, default=42, help="random seed for reproducibility")
    parser.add_argument("--output", type=Path, default=Path("demo-flows.json"))
    args = parser.parse_args()

    flows = generate_flows(args.count, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(flows, indent=2) + "\n", encoding="utf-8")
    sys.stdout.write(f"Wrote {len(flows)} flow records to {args.output}\n")


if __name__ == "__main__":
    main()
