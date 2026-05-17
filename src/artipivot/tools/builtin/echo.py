"""Built-in: echo tool."""

from langchain_core.tools import tool


@tool
def echo(message: str) -> str:
    """回显给定的消息。Echo back the given message."""
    return f"[echo] {message}"
