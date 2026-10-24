"""NEXUS backend - FastAPI application."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from . import __version__
from .chat import ChatTurn
from .config import get_settings
from .db import Store
from .providers import build_provider
from .schemas import (
    ChatRequest,
    ConversationDetail,
    ConversationSummary,
    CreateConversation,
    FileEntry,
    RenameConversation,
)
from .tools import ToolError, build_registry
from .tools.files import list_directory
from .tools.paths import display_path

log = logging.getLogger("nexus")
HEARTBEAT_SECONDS = 15.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    store = Store(settings.db_path)
    interrupted = store.mark_interrupted_streams()
    if interrupted:
        log.info("Marked %d interrupted replies as stopped", interrupted)
    app.state.settings = settings
    app.state.store = store
    app.state.registry = build_registry()
    app.state.provider = build_provider(settings)
    try:
        yield
    finally:
        aclose = getattr(app.state.provider, "aclose", None)
        if aclose:
            await aclose()
        store.close()


app = FastAPI(title="NEXUS backend", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["content-type"],
)


def error_body(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, **extra}}


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    detail = (
        exc.detail
        if isinstance(exc.detail, dict)
        else {"code": "http_error", "message": str(exc.detail)}
    )
    return JSONResponse({"error": detail}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    problems = [
        {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]}
        for e in exc.errors()
    ]
    first = problems[0] if problems else {"field": "", "message": "Invalid input"}
    message = f"{first['field']}: {first['message']}" if first["field"] else first["message"]
    return JSONResponse(error_body("invalid_input", message, details=problems), status_code=422)


def not_found(what: str) -> HTTPException:
    return HTTPException(404, {"code": "not_found", "message": f"{what} not found."})


# --- health & config ----------------------------------------------------------


@app.get("/api/health")
async def health(request: Request) -> dict[str, Any]:
    s = request.app.state.settings
    store: Store = request.app.state.store
    provider = request.app.state.provider
    resolved = s.resolved_provider
    # Providers that can probe themselves cheaply (e.g. a local Ollama) report readiness.
    probe = getattr(provider, "health", None)
    readiness: dict[str, Any] = await probe() if probe else {"ready": None, "detail": None}
    return {
        "status": "ok",
        "version": __version__,
        "database": "ok" if store.ping() else "error",
        "provider": {
            "name": resolved,
            "configured": provider is not None,
            "demo": resolved == "demo",
            "model": provider.model if provider else s.active_model,
            "ready": readiness["ready"],
            "effort": s.effort if resolved == "anthropic" else None,
            "refusal_fallback": s.refusal_fallback if resolved == "anthropic" else None,
            "message": {
                "anthropic": (
                    "Anthropic credentials loaded server-side. They are verified on the "
                    "first message."
                ),
                "ollama": readiness["detail"] or "Local model via Ollama.",
                "demo": "Demo mode: replies are canned text and no tools run.",
                "unconfigured": (
                    "No AI provider configured. Set NEXUS_PROVIDER=ollama in backend/.env to "
                    "use a free local model, or add ANTHROPIC_API_KEY, then restart the backend."
                ),
            }[resolved],
        },
        "tools": {
            "available": [t.name for t in request.app.state.registry.available()],
            "approved_directories": len(s.allowed_dir_list),
        },
    }


@app.get("/api/tools")
async def tools(request: Request) -> dict[str, Any]:
    registry = request.app.state.registry
    available = {t.name for t in registry.available()}
    return {
        "approval_flow_available": registry.approval_flow_available,
        "tools": [
            {**t.describe(), "enabled": t.name in available}
            for t in sorted(registry.tools.values(), key=lambda t: (not t.implemented, t.name))
        ],
    }


# --- files (read-only browsing of approved directories) -----------------------


@app.get("/api/files/roots")
async def file_roots(request: Request) -> dict[str, Any]:
    roots = request.app.state.settings.allowed_dir_list
    return {"roots": [{"path": str(r), "display": display_path(r), "name": r.name} for r in roots]}


@app.get("/api/files/list")
async def file_list(request: Request, path: str) -> dict[str, Any]:
    roots = request.app.state.settings.allowed_dir_list
    try:
        base, entries = await asyncio.to_thread(list_directory, path, roots)
    except ToolError as exc:
        status = 404 if exc.code == "not_found" else 403 if exc.code.startswith("path") else 400
        raise HTTPException(status, {"code": exc.code, "message": str(exc)}) from None
    return {
        "path": str(base),
        "display": display_path(base),
        "entries": [FileEntry(**e).model_dump() for e in entries],
    }


# --- conversations -------------------------------------------------------------


@app.get("/api/conversations", response_model=list[ConversationSummary])
async def list_conversations(request: Request) -> list[dict[str, Any]]:
    return request.app.state.store.list_conversations()  # type: ignore[no-any-return]


@app.post("/api/conversations", response_model=ConversationSummary, status_code=201)
async def create_conversation(request: Request, body: CreateConversation) -> dict[str, Any]:
    from .chat import DEFAULT_TITLE, build_system_prompt

    s = request.app.state.settings
    registry = request.app.state.registry
    provider = request.app.state.provider
    names = [t.name for t in registry.available()] if provider and provider.supports_tools else []
    conv = request.app.state.store.create_conversation(
        body.title or DEFAULT_TITLE, build_system_prompt(s.allowed_dir_list, sorted(names))
    )
    return {**conv, "message_count": 0}


@app.get("/api/conversations/{cid}", response_model=ConversationDetail)
async def get_conversation(request: Request, cid: str) -> dict[str, Any]:
    store: Store = request.app.state.store
    conv = store.get_conversation(cid)
    if conv is None:
        raise not_found("Conversation")
    messages = store.get_chat_messages(cid)
    return {**conv, "message_count": len(messages), "messages": messages}


@app.patch("/api/conversations/{cid}", response_model=ConversationSummary)
async def rename_conversation(
    request: Request, cid: str, body: RenameConversation
) -> dict[str, Any]:
    store: Store = request.app.state.store
    if not store.rename_conversation(cid, body.title):
        raise not_found("Conversation")
    conv = store.get_conversation(cid)
    assert conv is not None
    return {**conv, "message_count": len(store.get_chat_messages(cid))}


@app.delete("/api/conversations/{cid}", status_code=204)
async def delete_conversation(request: Request, cid: str) -> None:
    if not request.app.state.store.delete_conversation(cid):
        raise not_found("Conversation")


# --- chat (server-sent events) -------------------------------------------------


def sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n"


async def with_heartbeat(events: AsyncGenerator[dict[str, Any]]) -> AsyncIterator[str]:
    """Interleave SSE comments so idle proxies keep the stream open while the model thinks.

    The producer runs as its own task; if the client disconnects, this generator is
    cancelled and cancels the producer, which records the reply as stopped.
    """
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    async def produce() -> None:
        try:
            async with contextlib.aclosing(events):
                async for ev in events:
                    await queue.put(("event", ev))
        except Exception as exc:
            log.exception("chat stream failed")
            await queue.put(("crash", exc))
        finally:
            await queue.put(("end", None))

    task = asyncio.create_task(produce())
    try:
        while True:
            try:
                kind, item = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if kind == "event":
                yield sse(item)
            elif kind == "crash":
                yield sse({"type": "error", "code": "internal_error", "message": "Internal error."})
            else:
                break
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


@app.post("/api/chat")
async def chat(request: Request, body: ChatRequest) -> StreamingResponse:
    store: Store = request.app.state.store
    provider = request.app.state.provider
    if provider is None:
        raise HTTPException(
            503,
            {
                "code": "provider_not_configured",
                "message": (
                    "No AI provider is configured. Set NEXUS_PROVIDER=ollama in backend/.env "
                    "for a free local model (or add ANTHROPIC_API_KEY), then restart the backend."
                ),
            },
        )
    if body.conversation_id and store.get_conversation(body.conversation_id) is None:
        raise not_found("Conversation")

    turn = ChatTurn(
        store=store,
        provider=provider,
        registry=request.app.state.registry,
        settings=request.app.state.settings,
    )
    return StreamingResponse(
        with_heartbeat(turn.run(body.conversation_id, body.message)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
