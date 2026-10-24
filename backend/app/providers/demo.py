"""Explicitly labeled offline demo provider.

It never calls a model and never requests tools, so nothing in the UI can
suggest that real work was done.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from .base import ProviderEvent, TextDelta, TurnComplete


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if msg["role"] != "user":
            continue
        for block in msg["content"]:
            if isinstance(block, dict) and block.get("type") == "text":
                return str(block.get("text", ""))
    return ""


class DemoProvider:
    name = "demo"
    model = "demo"
    supports_tools = False
    persists_replies = False

    async def stream_turn(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[ProviderEvent]:
        said = _last_user_text(messages).strip()
        quoted = said if len(said) <= 280 else said[:277] + "..."
        reply = (
            "**Demo mode - no AI model is connected.**\n\n"
            f"You said: “{quoted}”\n\n"
            "This reply is canned text from the backend. No model was called, and no "
            "files were searched or read. To get real answers, set `ANTHROPIC_API_KEY` "
            "in `backend/.env`, remove `NEXUS_PROVIDER=demo`, and restart the backend."
        )
        for i in range(0, len(reply), 12):
            await asyncio.sleep(0.015)
            yield TextDelta(reply[i : i + 12])
        yield TurnComplete(
            content=[{"type": "text", "text": reply}],
            stop_reason="end_turn",
            tool_calls=[],
            model=self.model,
        )
