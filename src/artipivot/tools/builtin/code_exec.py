"""Stub: code_exec tool."""

from langchain_core.tools import tool


@tool
def code_exec(code: str, language: str = "python") -> str:
    """Execute code in a sandboxed environment and return the output.

    This is a stub implementation for P0 development.
    """
    return f"[STUB] code_exec: language={language}, code_length={len(code)}"
