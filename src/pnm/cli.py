"""Command-line entry point for PNM experiments."""

from __future__ import annotations

import argparse
from pathlib import Path

from pnm.config import load_experiment_config


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(description="Validate and prepare a PNM experiment.")
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to a TOML experiment configuration.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate a configuration and report the selected experiment."""
    args = build_parser().parse_args(argv)
    config = load_experiment_config(args.config)

    print(f"Experiment: {config.name}")
    print(f"Seed: {config.seed}")
    print(f"Workload: {config.workload_name}")
    print(f"Memory: {config.memory_type}")
    print(f"Near-memory enabled: {config.near_memory_enabled}")
    print(f"Output directory: {config.output_directory}")
    return 0
