from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.chat import ChatTurn
from app.config import Settings
from app.db import Store
from app.providers.ollama_provider import NO_TOOLS_NOTE, OllamaProvider, to_ollama_messages
from app.tools import build_registry
from tests import fake_ollama
from tests.conftest import _free_port, make_client
from tests.test_api import chat


@pytest.fixture
def client(monkeypatch, workspace, fake_ollama_url):  # type: ignore[no-untyped-def]
    fake_ollama.REQUESTS.clear()
    with make_client(
        monkeypatch, workspace, NEXUS_PROVIDER="ollama", NEXUS_OLLAMA_URL=fake_ollama_url
    ) as c:
        yield c


def test_transcript_translation() -> None:
    history = [
        {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "", "signature": "sig"},
                {"type": "text", "text": "Checking."},
                {"type": "tool_use", "id": "toolu_1", "name": "list_files", "input": {}},
            ],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "A, B"}],
        },
    ]
    out = to_ollama_messages("SYS", history)
    assert out == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "Checking.",
            "tool_calls": [{"function": {"name": "list_files", "arguments": {}}}],
        },
        {"role": "tool", "content": "A, B", "tool_name": "list_files"},
    ]


def test_health_reports_readiness(client, monkeypatch, workspace, fake_ollama_url) -> None:  # type: ignore[no-untyped-def]
    p = client.get("/api/health").json()["provider"]
    assert p["name"] == "ollama" and p["configured"] and p["ready"] is True
    assert p["model"] == "fake-tools" and p["effort"] is None
    with make_client(
        monkeypatch,
        workspace,
        NEXUS_PROVIDER="ollama",
        NEXUS_OLLAMA_URL=fake_ollama_url,
        NEXUS_OLLAMA_MODEL="missing-model",
    ) as c:
        p = c.get("/api/health").json()["provider"]
        assert p["ready"] is False and "ollama pull missing-model" in p["message"]
    with make_client(
        monkeypatch,
        workspace,
        NEXUS_PROVIDER="ollama",
        NEXUS_OLLAMA_URL=f"http://127.0.0.1:{_free_port()}",
    ) as c:
        p = c.get("/api/health").json()["provider"]
        assert p["ready"] is False and "not reachable" in p["message"]


def test_chat_streams_and_persists(client) -> None:  # type: ignore[no-untyped-def]
    events = chat(client, "Hello local model")
    assert events[0]["provider"] == "ollama" and events[0]["model"] == "fake-tools"
    assert {"type": "status", "state": "thinking"} in events
    text = "".join(e.get("delta", "") for e in events)
    assert "You said: Hello local model" in text and "Let me consider" not in text
    assert events[-1]["status"] == "complete"

    req = fake_ollama.REQUESTS[-1]
    assert req["think"] is True and req["stream"] is True
    assert req["options"]["num_ctx"] == 16384
    assert {t["function"]["name"] for t in req["tools"]} == {
        "list_files",
        "search_files",
        "read_file",
    }
    cid = events[0]["conversation_id"]
    conv = client.get(f"/api/conversations/{cid}").json()
    assert [m["status"] for m in conv["messages"]] == ["complete", "complete"]

    events = chat(client, "Second message", cid)
    sent = fake_ollama.REQUESTS[-1]["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
    assert "Hello local model" in sent[2]["content"]
    assert "messages: 4" in "".join(e.get("delta", "") for e in events)


def test_tool_loop(client) -> None:  # type: ignore[no-untyped-def]
    events = chat(client, "please list my files")
    end = next(e for e in events if e["type"] == "tool_end")
    assert end["name"] == "list_files" and end["ok"] is True
    assert "Tool list_files succeeded" in "".join(e.get("delta", "") for e in events)
    tool_msg = fake_ollama.REQUESTS[-1]["messages"][-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_name"] == "list_files"
    assert "Approved directories" in tool_msg["content"]
    conv = client.get(f"/api/conversations/{events[0]['conversation_id']}").json()
    assert [p["type"] for p in conv["messages"][1]["parts"]] == ["tool", "text"]


def test_tool_safeguards_apply(client) -> None:  # type: ignore[no-untyped-def]
    events = chat(client, "read /etc/passwd")
    end = next(e for e in events if e["type"] == "tool_end")
    assert end["ok"] is False and end["error_code"] == "path_not_allowed"
    assert "root:" not in fake_ollama.REQUESTS[-1]["messages"][-1]["content"]


def test_model_without_tools(monkeypatch, workspace, fake_ollama_url) -> None:  # type: ignore[no-untyped-def]
    with make_client(
        monkeypatch,
        workspace,
        NEXUS_PROVIDER="ollama",
        NEXUS_OLLAMA_URL=fake_ollama_url,
        NEXUS_OLLAMA_MODEL="fake-plain",
    ) as c:
        events = chat(c, "please list my files")
        notice = next(e for e in events if e["type"] == "notice")
        assert "can't call tools" in notice["text"]
        assert not [e for e in events if e["type"].startswith("tool")]
        req = fake_ollama.REQUESTS[-1]
        assert "tools" not in req and "think" not in req
        assert req["messages"][0]["content"].endswith(NO_TOOLS_NOTE)


def test_unreachable_and_missing_model(monkeypatch, workspace, fake_ollama_url) -> None:  # type: ignore[no-untyped-def]
    with make_client(
        monkeypatch,
        workspace,
        NEXUS_PROVIDER="ollama",
        NEXUS_OLLAMA_URL=f"http://127.0.0.1:{_free_port()}",
    ) as c:
        events = chat(c, "hi")
        err = next(e for e in events if e["type"] == "error")
        assert err["code"] == "ollama_unreachable" and "ollama serve" in err["message"]
        conv = c.get(f"/api/conversations/{events[0]['conversation_id']}").json()
        assert conv["messages"][1]["status"] == "error"
    with make_client(
        monkeypatch,
        workspace,
        NEXUS_PROVIDER="ollama",
        NEXUS_OLLAMA_URL=fake_ollama_url,
        NEXUS_OLLAMA_MODEL="missing-model",
    ) as c:
        err = next(e for e in chat(c, "hi") if e["type"] == "error")
        assert (
            err["code"] == "model_not_installed" and "ollama pull missing-model" in err["message"]
        )


def test_cancel_mid_stream(tmp_path: Path, fake_ollama_url: str) -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        NEXUS_PROVIDER="ollama",
        NEXUS_OLLAMA_URL=fake_ollama_url,
        NEXUS_OLLAMA_MODEL="fake-tools",
    )
    store = Store(tmp_path / "cancel.db")

    async def scenario() -> str:
        provider = OllamaProvider(settings)
        turn = ChatTurn(
            store=store, provider=provider, registry=build_registry(), settings=settings
        )
        gen = turn.run(None, "please be slow")
        cid = ""
        texts = 0
        async for ev in gen:
            if ev["type"] == "meta":
                cid = ev["conversation_id"]
            if ev["type"] == "text":
                texts += 1
                if texts == 5:
                    break
        await gen.aclose()  # what a client disconnect does to the stream
        await provider.aclose()
        return cid

    cid = asyncio.run(scenario())
    reply = store.get_chat_messages(cid)[-1]
    assert reply["status"] == "stopped" and reply["parts"][0]["text"].startswith("Streaming")
    # Only the user turn reached the model transcript; the next request stays valid.
    assert [m["role"] for m in store.get_api_messages(cid)] == ["user"]
