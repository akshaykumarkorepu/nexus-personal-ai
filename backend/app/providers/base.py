"""Provider-neutral interface for model calls.

A provider streams one model turn and finishes with a ``TurnComplete`` holding
the assistant message exactly as it must be replayed on the next request.
Running tools and looping is the orchestrator's job (``app.chat``), not the
provider's.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ThinkingStarted:
    pass


@dataclass(frozen=True)
class Notice:
    """A non-fatal note for the user, shown inline in the reply."""

    text: str
    level: str = "warning"


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: Any


@dataclass(frozen=True)
class TurnComplete:
    content: list[dict[str, Any]]
    stop_reason: str | None
    tool_calls: list[ToolCall]
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    refusal_explanation: str | None = None


ProviderEvent = TextDelta | ThinkingStarted | Notice | TurnComplete


class ProviderError(Exception):
    """A model call failed. ``message`` is safe to show to the user."""

    def __init__(self, code: str, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class Provider(Protocol):
    name: str
    model: str
    # False for providers that must never be offered tools (e.g. demo mode).
    supports_tools: bool
    # False when replies should not enter the model-facing transcript.
    persists_replies: bool

    def stream_turn(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[ProviderEvent]: ...
