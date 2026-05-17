"""Built-in: get current time tool."""

from datetime import datetime

from langchain_core.tools import tool


@tool
def current_time() -> str:
    """获取当前日期和时间（yyyy-MM-dd HH:mm:ss 格式）。Get the current date and time in yyyy-MM-dd HH:mm:ss format."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
