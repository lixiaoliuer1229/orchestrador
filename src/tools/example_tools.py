"""Sample tools that the agent can call."""
from datetime import datetime

from langchain_core.tools import tool


@tool
def get_current_time() -> str:
    """Return the current UTC time in ISO 8601 format."""
    return datetime.utcnow().isoformat()


@tool
def add_numbers(a: float, b: float) -> float:
    """Add two numbers and return the sum."""
    return a + b


DEFAULT_TOOLS = [get_current_time, add_numbers]

__all__ = ["DEFAULT_TOOLS", "get_current_time", "add_numbers"]