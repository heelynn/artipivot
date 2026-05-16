"""Transform YAML loader -- load transform definitions from transforms.yaml."""

from __future__ import annotations

from pathlib import Path

import structlog
import yaml

from artipivot.transforms.registry import TransformRegistry

logger = structlog.get_logger("artipivot.transforms")


def load_transforms_seed(
    registry: TransformRegistry,
    seed_dir: str | Path = "config/seed",
) -> list[str]:
    """Load transform definitions from transforms.yaml and register them.

    Returns list of successfully registered transform names.
    Failed imports are logged and skipped.
    """
    path = Path(seed_dir) / "transforms.yaml"
    if not path.exists():
        return []

    data = yaml.safe_load(path.read_text())
    if not data or "transforms" not in data:
        return []

    registered: list[str] = []
    for name, cfg in data["transforms"].items():
        module_path = cfg["module"]
        fn_name = cfg["function"]
        try:
            registry.register_module(name, module_path, fn_name, source="yaml")
            registered.append(name)
        except (ImportError, AttributeError):
            logger.warning(
                "seed_load_failed", name=name, module=module_path, function=fn_name
            )
    return registered
