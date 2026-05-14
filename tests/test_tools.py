"""Tests for tool layer."""

from __future__ import annotations

import pytest

from artipivot.tools.builtin.code_exec import code_exec
from artipivot.tools.builtin.file_io import file_io
from artipivot.tools.builtin.web_search import web_search
from artipivot.tools.registry import ToolRegistry


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        reg.register(web_search)
        assert reg.get("web_search") is not None
        assert reg.get("nonexistent") is None

    def test_get_for_agent(self):
        reg = ToolRegistry()
        reg.register(web_search)
        reg.register(code_exec)
        reg.register(file_io)

        tools = reg.get_for_agent(["web_search", "code_exec"])
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert names == {"web_search", "code_exec"}

    def test_get_for_agent_unknown_ignored(self):
        reg = ToolRegistry()
        reg.register(web_search)
        tools = reg.get_for_agent(["web_search", "nonexistent"])
        assert len(tools) == 1

    def test_get_tool_node(self):
        reg = ToolRegistry()
        reg.register(web_search)
        reg.register(code_exec)
        node = reg.get_tool_node(["web_search"])
        assert node is not None

    def test_names(self):
        reg = ToolRegistry()
        reg.register(web_search)
        reg.register(code_exec)
        assert set(reg.names) == {"web_search", "code_exec"}


class TestBuiltinTools:
    def test_web_search(self):
        result = web_search.invoke({"query": "test", "max_results": 3})
        assert "STUB" in result
        assert "test" in result

    def test_code_exec(self):
        result = code_exec.invoke({"code": "print('hello')", "language": "python"})
        assert "STUB" in result

    def test_file_io_read(self):
        result = file_io.invoke({"path": "/tmp/test.txt", "action": "read"})
        assert "STUB" in result

    def test_file_io_write(self):
        result = file_io.invoke({"path": "/tmp/test.txt", "content": "hello", "action": "write"})
        assert "STUB" in result
