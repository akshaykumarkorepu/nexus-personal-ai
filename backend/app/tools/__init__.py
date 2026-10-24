"""Tool registry and built-in tools."""

from .files import FILE_TOOLS
from .planned import PLANNED_TOOLS
from .registry import (
    PermissionLevel,
    Tool,
    ToolContext,
    ToolError,
    ToolOutput,
    ToolRegistry,
    ToolResult,
)

__all__ = [
    "PermissionLevel",
    "Tool",
    "ToolContext",
    "ToolError",
    "ToolOutput",
    "ToolRegistry",
    "ToolResult",
    "build_registry",
]


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in (*FILE_TOOLS, *PLANNED_TOOLS):
        registry.register(tool)
    return registry
