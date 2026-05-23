"""Stub: code_exec tool."""

from langchain_core.tools import tool


@tool
def code_exec(code: str, language: str = "python") -> str:
    """执行代码。Execute code in a sandboxed environment.

    This is a stub implementation for P0 development.
    """
    return f"[STUB] code_exec: executed {language} code ({len(code)} chars)"
