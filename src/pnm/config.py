"""Typed loading and validation for experiment configuration files."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExperimentConfig:
    """The minimum configuration required to identify a reproducible run."""

    name: str
    seed: int
    workload_name: str
    batch_size: int
    memory_type: str
    near_memory_enabled: bool
    output_directory: Path


def load_experiment_config(path: Path) -> ExperimentConfig:
    """Load and validate an experiment configuration from a TOML file.

    Output paths are kept relative to the repository unless an absolute path is
    intentionally provided in the configuration.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with path.open("rb") as config_file:
        raw = tomllib.load(config_file)

    try:
        experiment = raw["experiment"]
        workload = raw["workload"]
        hardware = raw["hardware"]
        output = raw["output"]
        config = ExperimentConfig(
            name=_required_string(experiment, "name"),
            seed=_required_int(experiment, "seed"),
            workload_name=_required_string(workload, "name"),
            batch_size=_positive_int(workload, "batch_size"),
            memory_type=_required_string(hardware, "memory_type"),
            near_memory_enabled=_required_bool(hardware, "near_memory_enabled"),
            output_directory=Path(_required_string(output, "directory")),
        )
    except KeyError as error:
        raise ValueError(f"Missing required configuration key: {error.args[0]}") from error

    return config


def _required_string(section: dict[str, object], key: str) -> str:
    value = section[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _required_int(section: dict[str, object], key: str) -> int:
    value = section[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _positive_int(section: dict[str, object], key: str) -> int:
    value = _required_int(section, key)
    if value <= 0:
        raise ValueError(f"{key} must be positive")
    return value


def _required_bool(section: dict[str, object], key: str) -> bool:
    value = section[key]
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value
