"""Run a PNM experiment from the repository root.

Usage:
    python scripts/run_experiment.py --config configs/baseline.toml
"""

from pnm.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
