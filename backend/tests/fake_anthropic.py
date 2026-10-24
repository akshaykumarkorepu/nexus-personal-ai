"""TEST-ONLY stand-in for the Anthropic Messages API (streaming).

It speaks the real SSE wire format, so the actual Anthropic SDK and NEXUS's
provider adapter run unmodified against it. Behaviour is scripted from the last
user message:

* last message holds tool results  -> a text answer quoting the first result
* "list my files"                   -> thinking, then a list_files tool call
* "read <path>"                     -> read_file tool call for <path>
* "search <term>"                   -> search_files tool call
* "slow"                            -> streams text slowly (for stop tests)
* anything else                     -> thinking, then an echo answer

Run standalone:  python -m tests.fake_anthropic --port 8787
Never point a real deployment at this.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
REQUESTS: list[dict[str, Any]] = []
HEADERS: list[dict[str, str]] = []


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _last_user_blocks(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for m in reversed(messages):
        if m["role"] == "user":
            c = m["content"]
            return [{"type": "text", "text": c}] if isinstance(c, str) else list(c)
    return []


def _plan(body: dict[str, Any]) -> tuple[list[dict[str, Any]], str, float]:
    """Return (content blocks, stop_reason, per-chunk delay)."""
    blocks = _last_user_blocks(body["messages"])
    results = [b for b in blocks if b.get("type") == "tool_result"]
    thinking = {"type": "thinking", "thinking": "", "signature": f"sig-{len(REQUESTS)}"}
    if results:
        first = results[0]
        content = first.get("content")
        text = content if isinstance(content, str) else json.dumps(content)
        status = "failed" if first.get("is_error") else "succeeded"
        return (
            [{"type": "text", "text": f"Tool {status}. First result:\n\n{text[:400]}"}],
            "end_turn",
            0.0,
        )
    text = " ".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    low = text.lower()
    tool_id = f"toolu_{len(REQUESTS):04d}"
    if "list my files" in low:
        call = {"type": "tool_use", "id": tool_id, "name": "list_files", "input": {}}
        return [thinking, {"type": "text", "text": "Checking."}, call], "tool_use", 0.0
    if m := re.search(r"\bread (\S+)", text):
        call = {"type": "tool_use", "id": tool_id, "name": "read_file", "input": {"path": m[1]}}
        return [call], "tool_use", 0.0
    if m := re.search(r"\bsearch (\S+)", text):
        call = {
            "type": "tool_use",
            "id": tool_id,
            "name": "search_files",
            "input": {"query": m[1]},
        }
        return [call], "tool_use", 0.0
    history = len(body["messages"])
    answer = f"Fake model reply. You said: {text.strip()[:200]} (history: {history} messages)"
    if "slow" in low:
        return [{"type": "text", "text": "Streaming slowly " + "tick " * 200}], "end_turn", 0.05
    return [thinking, {"type": "text", "text": answer}], "end_turn", 0.0


async def _stream(body: dict[str, Any]) -> AsyncIterator[str]:
    blocks, stop_reason, delay = _plan(body)
    yield _sse(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": f"msg_fake_{len(REQUESTS)}",
                "type": "message",
                "role": "assistant",
                "model": body["model"],
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 42, "output_tokens": 1},
            },
        },
    )
    for i, block in enumerate(blocks):
        if block["type"] == "thinking":
            start = {"type": "thinking", "thinking": "", "signature": ""}
            yield _sse(
                "content_block_start",
                {"type": "content_block_start", "index": i, "content_block": start},
            )
            yield _sse(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": i,
                    "delta": {"type": "signature_delta", "signature": block["signature"]},
                },
            )
        elif block["type"] == "text":
            yield _sse(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": i,
                    "content_block": {"type": "text", "text": ""},
                },
            )
            words = re.findall(r"\S+\s*|\s+", block["text"])
            for w in words:
                if delay:
                    await asyncio.sleep(delay)
                yield _sse(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": i,
                        "delta": {"type": "text_delta", "text": w},
                    },
                )
        elif block["type"] == "tool_use":
            start = {"type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}
            yield _sse(
                "content_block_start",
                {"type": "content_block_start", "index": i, "content_block": start},
            )
            yield _sse(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": i,
                    "delta": {
                        "type": "input_json_delta",
                        "partial_json": json.dumps(block["input"]),
                    },
                },
            )
        yield _sse("content_block_stop", {"type": "content_block_stop", "index": i})
    yield _sse(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": 17},
        },
    )
    yield _sse("message_stop", {"type": "message_stop"})


@app.post("/v1/messages")
async def messages(request: Request) -> Any:
    body = await request.json()
    HEADERS.append({k.lower(): v for k, v in request.headers.items()})
    REQUESTS.append(body)
    presented = request.headers.get("x-api-key") or request.headers.get("authorization", "")
    if presented.removeprefix("Bearer ") == "invalid-key":
        return JSONResponse(
            {
                "type": "error",
                "error": {"type": "authentication_error", "message": "invalid x-api-key"},
            },
            status_code=401,
        )
    if not body.get("stream"):
        return JSONResponse(
            {
                "type": "error",
                "error": {"type": "invalid_request_error", "message": "fake server only streams"},
            },
            status_code=400,
        )
    return StreamingResponse(_stream(body), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8787)
    uvicorn.run(app, host="127.0.0.1", port=parser.parse_args().port, log_level="warning")
