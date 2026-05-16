"""TransformRegistry -- central registry for transform functions."""

from __future__ import annotations

import importlib
import inspect
import sys
import threading
from collections.abc import Callable
from typing import Any

import structlog

logger = structlog.get_logger("artipivot.transforms")

# Type alias: a transform receives a dict and returns a dict.
# Both sync and async callables are accepted.
TransformFn = Callable[[dict[str, Any]], dict[str, Any]]


class TransformRegistry:
    """Central registry for transform functions.

    Thread-safe. Supports:
    - Manual registration: register(name, fn)
    - Dynamic import: register_module(name, module_path, fn_name)
    - Entry-point auto-discovery: discover_entry_points()
    - Hot-reload: re-register replaces the function reference without graph rebuild
    """

    ENTRY_POINT_GROUP = "artipivot.transforms"

    def __init__(self) -> None:
        self._transforms: dict[str, TransformFn] = {}
        self._metadata: dict[str, dict[str, str]] = {}
        self._lock = threading.RLock()

    # -- Registration --

    def register(
        self, name: str, fn: TransformFn, *, source: str = "manual"
    ) -> None:
        """Register (or replace) a transform function.

        Args:
            name: Unique transform name.
            fn: Callable[[dict], dict]. May be async.
            source: Origin for auditing ("manual", "entry_point", "yaml", "api",
                    "hot_reload").
        """
        if not callable(fn):
            raise TypeError(f"Transform must be callable, got {type(fn).__name__}")
        with self._lock:
            self._transforms[name] = fn
            self._metadata[name] = {
                "source": source,
                "is_async": inspect.iscoroutinefunction(fn),
                "module": getattr(fn, "__module__", ""),
                "qualname": getattr(fn, "__qualname__", ""),
            }
        logger.info("transform.registered", name=name, source=source)

    def unregister(self, name: str) -> None:
        """Remove a transform by name."""
        with self._lock:
            if name not in self._transforms:
                raise KeyError(f"Transform not found: {name}")
            del self._transforms[name]
            del self._metadata[name]
        logger.info("transform.unregistered", name=name)

    # -- Lookup --

    def get(self, name: str) -> TransformFn:
        """Get a transform function by name. Raises KeyError if not found."""
        with self._lock:
            fn = self._transforms.get(name)
        if fn is None:
            raise KeyError(
                f"Transform not found: {name}, "
                f"available: {list(self._transforms)}"
            )
        return fn

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._transforms

    def list_transforms(self) -> list[dict[str, Any]]:
        """Return metadata for all registered transforms."""
        with self._lock:
            return [{"name": name, **meta} for name, meta in self._metadata.items()]

    @property
    def names(self) -> list[str]:
        with self._lock:
            return list(self._transforms)

    # -- Discovery --

    def discover_entry_points(self) -> list[str]:
        """Auto-discover transforms from importlib.metadata entry points.

        Returns list of registered names.
        """
        from importlib.metadata import entry_points

        registered: list[str] = []
        try:
            eps = entry_points(group=self.ENTRY_POINT_GROUP)
        except Exception:
            logger.warning("entry_points_query_failed", exc_info=True)
            return registered

        for ep in eps:
            try:
                fn = ep.load()
                self.register(ep.name, fn, source="entry_point")
                registered.append(ep.name)
            except Exception:
                logger.warning(
                    "entry_point_failed", name=ep.name, value=ep.value, exc_info=True
                )
        logger.info("transform.discovered", count=len(registered))
        return registered

    def register_module(
        self,
        name: str,
        module_path: str,
        fn_name: str,
        *,
        source: str = "dynamic",
        reload: bool = False,
    ) -> None:
        """Dynamically import a module and register a function.

        Args:
            name: Registration name.
            module_path: Dotted module path, e.g. "my_transforms.merge".
            fn_name: Function name within the module.
            source: Origin tag for metadata.
            reload: If True, force reload the module even if already imported.
        """
        try:
            module = importlib.import_module(module_path)
            if reload and module_path in sys.modules:
                module = importlib.reload(module)
            fn = getattr(module, fn_name)
        except (ImportError, ModuleNotFoundError) as e:
            logger.error(
                "register_module_import_failed",
                name=name,
                module=module_path,
                error=str(e),
            )
            raise
        except AttributeError as e:
            logger.error(
                "register_module_fn_not_found",
                name=name,
                module=module_path,
                function=fn_name,
                error=str(e),
            )
            raise
        self.register(name, fn, source=source)

    # -- Invocation helper --

    async def invoke(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        """Invoke a transform by name. Handles both sync and async functions.

        Raises KeyError if transform not found.
        Propagates exceptions from the transform function with name context.
        """
        fn = self.get(name)
        with self._lock:
            is_async = self._metadata[name]["is_async"]
        try:
            if is_async:
                return await fn(data)
            return fn(data)
        except Exception as e:
            logger.error(
                "transform.invoke_failed",
                name=name,
                error=str(e),
                exc_info=True,
            )
            raise
