"""Transform node builder -- creates LangGraph nodes from registered transforms."""

from __future__ import annotations

from typing import Any

from artipivot.transforms.registry import TransformRegistry


def make_transform_node(
    transform_name: str,
    registry: TransformRegistry,
    *,
    input_key: str = "metadata",
    output_key: str = "metadata",
):
    """Create a LangGraph node function that applies a registered transform.

    The returned async function reads from state, invokes the transform,
    and writes the result back to state.  Because it calls
    registry.get() at execution time (not build time), hot-reloaded
    functions take effect immediately without a graph rebuild.

    Args:
        transform_name: Name in TransformRegistry.
        registry: The TransformRegistry instance.
        input_key: State key to read transform input from.
        output_key: State key to write transform output to.

    Returns:
        Async node function suitable for StateGraph.add_node().
    """

    async def transform_node(state: dict[str, Any], runtime) -> dict[str, Any]:
        input_data = state.get(input_key, {})
        try:
            result = await registry.invoke(transform_name, input_data)
        except KeyError as e:
            raise ValueError(
                f"Transform node '{transform_name}': transform not registered"
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Transform node '{transform_name}' failed: {e}"
            ) from e
        return {output_key: result}

    transform_node.__name__ = f"transform:{transform_name}"
    return transform_node
