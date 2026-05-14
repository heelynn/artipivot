"""Stub: file_io tool."""

from langchain_core.tools import tool


@tool
def file_io(path: str, content: str | None = None, action: str = "read") -> str:
    """Read or write files on the filesystem.

    This is a stub implementation for P0 development.
    """
    if action == "read":
        return f"[STUB] file_io read: path={path}"
    return f"[STUB] file_io write: path={path}, content_length={len(content or '')}"
