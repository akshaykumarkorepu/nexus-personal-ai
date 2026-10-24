"""Ollama adapter: local models through Ollama's native streaming /api/chat endpoint.

NEXUS stores every conversation as content blocks (text, tool_use, tool_result,
thinking). This adapter translates that transcript into Ollama messages on the
way in and turns Ollama's reply back into the same blocks on the way out, so the
orchestrator, history, cancellation and tool loop work unchanged.
"""

from __future__ import annotations

import contextlib
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ..config import Settings
from .base import (
    Notice,
    ProviderError,
    ProviderEvent,
    TextDelta,
    ThinkingStarted,
    ToolCall,
    TurnComplete,
)

NO_TOOLS_NOTE = (
    "\n\nNote: the local model in use cannot call tools, so file tools are unavailable in "
    "this reply. Do not claim to have listed, searched or read any files."
)


def to_ollama_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Registry tool definitions -> Ollama/OpenAI-style function tools."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(b.get("text", ""))
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def to_ollama_messages(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """NEXUS transcript (content blocks) -> Ollama chat messages.

    Thinking blocks and other provider-specific blocks are dropped; tool results
    become ``role: "tool"`` messages tagged with the tool's name.
    """
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    tool_names: dict[str, str] = {}
    for msg in messages:
        blocks = msg["content"]
        if isinstance(blocks, str):
            blocks = [{"type": "text", "text": blocks}]
        if msg["role"] == "assistant":
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            calls = []
            for b in blocks:
                if b.get("type") == "tool_use":
                    tool_names[b["id"]] = b["name"]
                    calls.append({"function": {"name": b["name"], "arguments": b.get("input", {})}})
            entry: dict[str, Any] = {"role": "assistant", "content": text}
            if calls:
                entry["tool_calls"] = calls
            out.append(entry)
            continue
        texts: list[str] = []
        for b in blocks:
            if b.get("type") == "tool_result":
                out.append(
                    {
                        "role": "tool",
                        "content": _text_of(b.get("content", "")),
                        "tool_name": tool_names.get(b.get("tool_use_id", ""), ""),
                    }
                )
            elif b.get("type") == "text":
                texts.append(str(b.get("text", "")))
        if texts:
            out.append({"role": "user", "content": "\n".join(texts)})
    return out


class OllamaProvider:
    name = "ollama"
    supports_tools = True
    persists_replies = True

    def __init__(self, settings: Settings) -> None:
        self.model = settings.ollama_model
        self.base_url = settings.ollama_url.rstrip("/")
        self.options = {"num_ctx": settings.ollama_num_ctx, "num_predict": settings.max_tokens}
        # Generation can pause for a long time while a model loads; only the
        # connection itself should fail fast.
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(settings.request_timeout_seconds, connect=5.0),
        )
        self._capabilities: dict[str, set[str] | None] = {}

    async def aclose(self) -> None:
        await self.client.aclose()

    def _unreachable(self) -> ProviderError:
        return ProviderError(
            "ollama_unreachable",
            f"Cannot reach Ollama at {self.base_url}. Open the Ollama app or run `ollama serve`.",
        )

    async def capabilities(self) -> set[str] | None:
        """Model capabilities from /api/show (None if this Ollama doesn't report them)."""
        if self.model not in self._capabilities:
            try:
                res = await self.client.post("/api/show", json={"model": self.model})
            except httpx.TransportError:
                raise self._unreachable() from None
            if res.status_code == 404:
                raise ProviderError(
                    "model_not_installed",
                    f"Ollama model '{self.model}' is not installed. Run: ollama pull {self.model}",
                    status=404,
                )
            caps = res.json().get("capabilities") if res.is_success else None
            self._capabilities[self.model] = set(caps) if isinstance(caps, list) else None
        return self._capabilities[self.model]

    async def health(self) -> dict[str, Any]:
        """Cheap readiness probe for /api/health (no generation)."""
        try:
            res = await self.client.get("/api/tags", timeout=2.0)
            names = {m.get("name") for m in res.json().get("models", [])}
        except (httpx.HTTPError, ValueError):
            return {
                "ready": False,
                "detail": f"Ollama is not reachable at {self.base_url}. Open the Ollama app or "
                "run `ollama serve`.",
            }
        wanted = {self.model, f"{self.model}:latest"}
        if not names & wanted:
            return {
                "ready": False,
                "detail": f"Ollama is running, but model '{self.model}' is not installed. "
                f"Run: ollama pull {self.model}",
            }
        return {"ready": True, "detail": f"Local model '{self.model}' via Ollama. No API key used."}

    async def stream_turn(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[ProviderEvent]:
        caps = await self.capabilities()
        use_tools = bool(tools) and (caps is None or "tools" in caps)
        if tools and not use_tools:
            yield Notice(
                f"'{self.model}' can't call tools, so file access is off for this reply. "
                "Use a tool-capable model such as qwen3 or llama3.1 for file tools."
            )
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": to_ollama_messages(
                system + ("" if use_tools or not tools else NO_TOOLS_NOTE), messages
            ),
            "stream": True,
            "options": self.options,
        }
        if use_tools:
            payload["tools"] = to_ollama_tools(tools)
        if caps is not None and "thinking" in caps:
            # Reasoning models (e.g. qwen3) think regardless; with think=false Ollama mixes
            # that reasoning into the answer text. Enabling it routes the reasoning to a
            # separate field, which is never shown or stored.
            payload["think"] = True

        text_parts: list[str] = []
        calls: list[ToolCall] = []
        done_reason: str | None = None
        usage: dict[str, int] = {}
        announced_thinking = False
        try:
            async with self.client.stream("POST", "/api/chat", json=payload) as res:
                if res.status_code >= 400:
                    await res.aread()
                    raise self._http_error(res)
                async for line in res.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if chunk.get("error"):
                        raise ProviderError("provider_error", f"Ollama: {chunk['error']}")
                    msg = chunk.get("message") or {}
                    if msg.get("thinking") and not announced_thinking:
                        announced_thinking = True
                        yield ThinkingStarted()
                    if msg.get("content"):
                        text_parts.append(msg["content"])
                        yield TextDelta(msg["content"])
                    for call in msg.get("tool_calls") or []:
                        fn = call.get("function") or {}
                        args = fn.get("arguments", {})
                        if isinstance(args, str):
                            # Some models send JSON text; the registry rejects anything
                            # that still isn't an object.
                            with contextlib.suppress(ValueError):
                                args = json.loads(args)
                        calls.append(
                            ToolCall(
                                id=f"call_{uuid.uuid4().hex[:24]}",
                                name=str(fn.get("name", "")),
                                input=args,
                            )
                        )
                    if chunk.get("done"):
                        done_reason = chunk.get("done_reason")
                        usage = {
                            "input_tokens": int(chunk.get("prompt_eval_count") or 0),
                            "output_tokens": int(chunk.get("eval_count") or 0),
                        }
        except httpx.TimeoutException:
            raise ProviderError("timeout", "Ollama took too long to respond.") from None
        except httpx.TransportError:
            raise self._unreachable() from None
        except ValueError:
            raise ProviderError("malformed_output", "Ollama sent an unreadable response.") from None

        content: list[dict[str, Any]] = []
        text = "".join(text_parts)
        if text:
            content.append({"type": "text", "text": text})
        content.extend(
            {"type": "tool_use", "id": c.id, "name": c.name, "input": c.input} for c in calls
        )
        if calls:
            stop_reason = "tool_use"
        elif done_reason == "length":
            stop_reason = "max_tokens"
        else:
            stop_reason = "end_turn"
        yield TurnComplete(
            content=content,
            stop_reason=stop_reason,
            tool_calls=calls,
            model=self.model,
            usage=usage,
        )

    def _http_error(self, res: httpx.Response) -> ProviderError:
        try:
            detail = str(res.json().get("error", ""))
        except ValueError:
            detail = res.text[:300]
        if res.status_code == 404:
            return ProviderError(
                "model_not_installed",
                f"Ollama model '{self.model}' is not installed. Run: ollama pull {self.model}",
                status=404,
            )
        return ProviderError(
            "provider_error", f"Ollama error ({res.status_code}): {detail}", status=res.status_code
        )
