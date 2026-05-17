"""Auto-discover all @tool-decorated functions in this package."""

from __future__ import annotations

import importlib
import pkgutil

from langchain_core.tools import BaseTool

_PACKAGE_DIR = __path__[0]


def discover() -> dict[str, BaseTool]:
    """Scan every module in this package and collect LangChain @tool instances."""
    tools: dict[str, BaseTool] = {}
    for info in pkgutil.iter_modules([_PACKAGE_DIR]):
        mod = importlib.import_module(f"{__name__}.{info.name}")
        for attr in vars(mod).values():
            if isinstance(attr, BaseTool):
                tools[attr.name] = attr
    return tools
