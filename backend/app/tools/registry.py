"""Registry of explicitly permitted tools.

Every tool declares a name, description, Pydantic input schema, handler and
permission level. The model never gets a tool that is not registered here, and
every call goes through ``ToolRegistry.execute``, which:

1. rejects unknown and not-yet-implemented tools,
2. refuses tools whose permission level needs user approval unless approved,
3. validates the raw model-supplied input against the schema,
4. runs the handler under a timeout, and
5. caps the size of what is sent back to the model.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError


class PermissionLevel(StrEnum):
    READ_ONLY = "read_only"  # reads approved local data; runs without prompting
    WRITE = "write"  # modifies files or app state; needs approval
    EXECUTE = "execute"  # runs processes; needs approval
    EXTERNAL = "external"  # acts outside this machine (browser, network); needs approval

    @property
    def requires_approval(self) -> bool:
        return self is not PermissionLevel.READ_ONLY


class ToolError(Exception):
    """An expected tool failure whose message is safe to show the model and user."""

    def __init__(self, message: str, code: str = "tool_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ToolContext:
    roots: list[Path]
    max_read_chars: int
    max_file_bytes: int
    timeout_seconds: float


@dataclass(frozen=True)
class ToolOutput:
    content: str  # sent to the model
    summary: str  # one line for the activity feed


Handler = Callable[[Any, ToolContext], Awaitable[ToolOutput]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    permission: PermissionLevel
    handler: Handler | None = None
    category: str = "general"

    @property
    def implemented(self) -> bool:
        return self.handler is not None

    def api_definition(self) -> dict[str, Any]:
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": schema,
            # Inputs stream as they are generated; we validate them ourselves below.
            "eager_input_streaming": True,
        }

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "permission": self.permission.value,
            "requires_approval": self.permission.requires_approval,
            "implemented": self.implemented,
            "input_schema": self.input_model.model_json_schema(),
        }


@dataclass
class ToolResult:
    ok: bool
    content: str
    summary: str
    duration_ms: int
    error_code: str | None = None


@dataclass
class ToolRegistry:
    tools: dict[str, Tool] = field(default_factory=dict)
    # No approval UI exists yet, so approval-gated tools are never offered to the
    # model. Flip this only once the frontend can collect explicit consent.
    approval_flow_available: bool = False

    def register(self, tool: Tool) -> None:
        if tool.name in self.tools:
            raise ValueError(f"duplicate tool name: {tool.name}")
        self.tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self.tools.get(name)

    def available(self) -> list[Tool]:
        """Tools the model may call right now."""
        return [
            t
            for t in self.tools.values()
            if t.implemented
            and (not t.permission.requires_approval or self.approval_flow_available)
        ]

    def api_definitions(self) -> list[dict[str, Any]]:
        # Sorted so the request prefix stays byte-identical between turns.
        return [t.api_definition() for t in sorted(self.available(), key=lambda t: t.name)]

    async def execute(
        self,
        name: str,
        raw_input: Any,
        ctx: ToolContext,
        *,
        approved: bool = False,
    ) -> ToolResult:
        start = time.monotonic()

        def fail(message: str, code: str, summary: str | None = None) -> ToolResult:
            return ToolResult(
                ok=False,
                content=f"Error ({code}): {message}",
                summary=summary or message,
                duration_ms=int((time.monotonic() - start) * 1000),
                error_code=code,
            )

        tool = self.tools.get(name)
        if tool is None:
            return fail(f"Unknown tool '{name}'.", "unknown_tool")
        if tool.handler is None:
            return fail(f"Tool '{name}' is not implemented yet.", "not_implemented")
        if tool.permission.requires_approval and not approved:
            return fail(
                f"Tool '{name}' needs explicit user approval ({tool.permission.value}).",
                "approval_required",
            )
        if not isinstance(raw_input, dict):
            return fail("Tool input must be a JSON object.", "invalid_input")
        try:
            args = tool.input_model.model_validate(raw_input)
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in e['loc']) or 'input'}: {e['msg']}"
                for e in exc.errors(include_url=False)
            )
            return fail(f"Invalid input - {problems}", "invalid_input", "Invalid tool input")

        try:
            output = await asyncio.wait_for(tool.handler(args, ctx), timeout=ctx.timeout_seconds)
        except TimeoutError:
            return fail(f"Timed out after {ctx.timeout_seconds:g}s.", "timeout")
        except ToolError as exc:
            return fail(str(exc), exc.code)
        except Exception as exc:  # never leak a traceback to the model
            return fail(f"Unexpected {type(exc).__name__}.", "internal_error")

        content = output.content
        if len(content) > ctx.max_read_chars:
            content = (
                content[: ctx.max_read_chars]
                + f"\n\n[Output truncated at {ctx.max_read_chars} characters.]"
            )
        return ToolResult(
            ok=True,
            content=content,
            summary=output.summary,
            duration_ms=int((time.monotonic() - start) * 1000),
        )
