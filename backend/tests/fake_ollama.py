"""TEST-ONLY stand-in for a local Ollama server (/api/tags, /api/show, /api/chat).

Streams NDJSON in the same shape as Ollama 0.32 (verified against a real
qwen3:4b): thinking arrives in ``message.thinking``, answer text in
``message.content``, tool calls in ``message.tool_calls`` with object arguments.

Models: ``fake-tools`` (tools + thinking), ``fake-plain`` (no tool support).
Behaviour comes from the last user message, like tests/fake_anthropic.py:
"list my files" -> list_files call, "read <path>" -> read_file call,
"slow" -> slow stream, tool results -> an answer quoting the first result.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
REQUESTS: list[dict[str, Any]] = []
MODELS = {"fake-tools": ["completion", "tools", "thinking"], "fake-plain": ["completion"]}


@app.get("/api/tags")
async def tags() -> dict[str, Any]:
    return {"models": [{"name": f"{m}:latest"} for m in MODELS]}


@app.post("/api/show")
async def show(request: Request) -> Any:
    model = (await request.json())["model"].removesuffix(":latest")
    if model not in MODELS:
        return JSONResponse({"error": f"model '{model}' not found"}, status_code=404)
    return {"capabilities": MODELS[model]}


def _line(message: dict[str, Any], done: bool = False, **extra: Any) -> str:
    chunk = {"model": "fake", "message": {"role": "assistant", **message}, "done": done, **extra}
    return json.dumps(chunk) + "\n"


async def _chat(body: dict[str, Any]) -> AsyncIterator[str]:
    last = body["messages"][-1]
    thinks = body.get("think") is True
    if thinks:
        yield _line({"content": "", "thinking": "Let me consider this."})
    if last["role"] == "tool":
        verdict = "failed" if last["content"].startswith("Error") else "succeeded"
        text = f"Tool {last['tool_name']} {verdict}. First result:\n\n{last['content'][:300]}"
        calls: list[dict[str, Any]] = []
    else:
        said = last["content"]
        calls = []
        text = f"Local reply. You said: {said[:200]} (messages: {len(body['messages'])})"
        if "list my files" in said.lower() and "tools" in body:
            calls = [{"function": {"name": "list_files", "arguments": {}}}]
            text = ""
        elif (m := re.search(r"\bread (\S+)", said)) and "tools" in body:
            calls = [{"function": {"name": "read_file", "arguments": {"path": m[1]}}}]
            text = ""
        elif "slow" in said.lower():
            text = "Streaming slowly " + "tick " * 200
    for word in re.findall(r"\S+\s*", text):
        if "slow" in text[:20].lower():
            await asyncio.sleep(0.05)
        yield _line({"content": word})
    if calls:
        yield _line({"content": "", "tool_calls": calls})
    yield _line({"content": ""}, done=True, done_reason="stop", prompt_eval_count=50, eval_count=12)


@app.post("/api/chat")
async def chat(request: Request) -> Any:
    body = await request.json()
    REQUESTS.append(body)
    if body["model"].removesuffix(":latest") not in MODELS:
        return JSONResponse({"error": f"model '{body['model']}' not found"}, status_code=404)
    return StreamingResponse(_chat(body), media_type="application/x-ndjson")
