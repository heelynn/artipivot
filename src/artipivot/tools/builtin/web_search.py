"""Stub: web_search tool."""

from langchain_core.tools import tool


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """Search the internet for the given query and return relevant web snippets.

    This is a stub implementation for P0 development.
    """
    return f"[STUB] web_search results for: '{query}' (max_results={max_results})"
