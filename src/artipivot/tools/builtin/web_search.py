"""Stub: web_search tool."""

from langchain_core.tools import tool


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """搜索网页。Search the web for information.

    This is a stub implementation for P0 development.
    """
    return f"[STUB] web_search results for: {query} (max_results={max_results})"
