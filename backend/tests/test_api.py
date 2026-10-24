from __future__ import annotations

from pathlib import Path

import pytest

from tests import fake_anthropic
from tests.conftest import make_client, read_sse


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, workspace: dict[str, Path], fake_api: str):  # type: ignore[no-untyped-def]
    fake_anthropic.REQUESTS.clear()
    fake_anthropic.HEADERS.clear()
    with make_client(
        monkeypatch, workspace, ANTHROPIC_API_KEY="test-key", ANTHROPIC_BASE_URL=fake_api
    ) as c:
        yield c


def chat(client, message: str, conversation_id: str | None = None):  # type: ignore[no-untyped-def]
    body = {"message": message, **({"conversation_id": conversation_id} if conversation_id else {})}
    with client.stream("POST", "/api/chat", json=body) as r:
        assert r.status_code == 200, r.read()
        return read_sse(r)


def test_health(client) -> None:  # type: ignore[no-untyped-def]
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["database"] == "ok"
    assert h["provider"]["name"] == "anthropic" and h["provider"]["configured"]
    assert h["provider"]["model"] == "claude-opus-5-5"
    assert "test-key" not in str(h)
    assert set(h["tools"]["available"]) == {"list_files", "search_files", "read_file"}


def test_conversation_streams_and_persists(client) -> None:  # type: ignore[no-untyped-def]
    events = chat(client, "Hello NEXUS")
    types = [e["type"] for e in events]
    assert types[0] == "meta" and types[-1] == "done"
    assert "status" in types  # thinking indicator
    text = "".join(e["delta"] for e in events if e["type"] == "text")
    assert "You said: Hello NEXUS" in text
    cid = events[0]["conversation_id"]

    # Request shape sent to the API.
    req = fake_anthropic.REQUESTS[-1]
    assert req["model"] == "claude-opus-5-5" and req["stream"] is True
    assert req["output_config"] == {"effort": "medium"}
    assert req["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in fake_anthropic.HEADERS[-1]["anthropic-beta"]
    assert {t["name"] for t in req["tools"]} == {"list_files", "search_files", "read_file"}

    # Persistence survives a reload.
    conv = client.get(f"/api/conversations/{cid}").json()
    assert conv["title"] == "Hello NEXUS"
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert conv["messages"][1]["status"] == "complete"
    assert "You said: Hello NEXUS" in conv["messages"][1]["parts"][0]["text"]
    assert client.get("/api/conversations").json()[0]["id"] == cid

    # Second turn: history is replayed append-only (thinking blocks included).
    first = fake_anthropic.REQUESTS[-1]
    events = chat(client, "And again", cid)
    second = fake_anthropic.REQUESTS[-1]
    assert second["system"] == first["system"] and second["tools"] == first["tools"]
    assert second["messages"][: len(first["messages"])] == first["messages"]
    assert second["messages"][1]["role"] == "assistant"
    assert second["messages"][1]["content"][0]["type"] == "thinking"
    assert second["messages"][1]["content"][0]["signature"]
    assert "history: 3 messages" in "".join(e.get("delta", "") for e in events)


def test_tool_loop_lists_files(client) -> None:  # type: ignore[no-untyped-def]
    events = chat(client, "please list my files")
    starts = [e for e in events if e["type"] == "tool_start"]
    ends = [e for e in events if e["type"] == "tool_end"]
    assert [e["name"] for e in starts] == ["list_files"]
    assert ends[0]["ok"] is True and "approved directories" in ends[0]["summary"]
    text = "".join(e["delta"] for e in events if e["type"] == "text")
    assert "Tool succeeded" in text and "approved" in text
    # The follow-up request carried the tool result back.
    last = fake_anthropic.REQUESTS[-1]["messages"][-1]
    assert last["content"][0]["type"] == "tool_result"
    conv = client.get(f"/api/conversations/{events[0]['conversation_id']}").json()
    parts = conv["messages"][1]["parts"]
    assert [p["type"] for p in parts] == ["text", "tool", "text"]
    assert parts[1]["status"] == "ok"


def test_tool_reads_pdf(client, workspace) -> None:  # type: ignore[no-untyped-def]
    path = workspace["approved"].resolve() / "lecture.pdf"
    events = chat(client, f"read {path}")
    end = next(e for e in events if e["type"] == "tool_end")
    assert end["ok"] is True
    assert "NEXUS revision notes" in "".join(e.get("delta", "") for e in events)


def test_tool_refuses_escape(client) -> None:  # type: ignore[no-untyped-def]
    events = chat(client, "read /etc/passwd")
    end = next(e for e in events if e["type"] == "tool_end")
    assert end["ok"] is False and end["error_code"] == "path_not_allowed"
    text = "".join(e.get("delta", "") for e in events)
    assert "Tool failed" in text and "root:" not in text


def test_invalid_requests(client) -> None:  # type: ignore[no-untyped-def]
    r = client.post("/api/chat", json={"message": "   "})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_input"
    r = client.post("/api/chat", json={"message": "hi", "conversation_id": "../etc"})
    assert r.status_code == 422
    r = client.post("/api/chat", json={"message": "hi", "conversation_id": "0" * 32})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert client.get("/api/files/list", params={"path": "/etc"}).status_code == 403


def test_conversation_crud(client) -> None:  # type: ignore[no-untyped-def]
    cid = client.post("/api/conversations", json={}).json()["id"]
    assert (
        client.patch(f"/api/conversations/{cid}", json={"title": "Renamed"}).json()["title"]
        == "Renamed"
    )
    assert client.delete(f"/api/conversations/{cid}").status_code == 204
    assert client.get(f"/api/conversations/{cid}").status_code == 404


def test_files_browse(client, workspace) -> None:  # type: ignore[no-untyped-def]
    roots = client.get("/api/files/roots").json()["roots"]
    assert len(roots) == 1
    listing = client.get("/api/files/list", params={"path": roots[0]["path"]}).json()
    names = {e["name"] for e in listing["entries"]}
    assert {"notes", "lecture.pdf"} <= names and ".env" not in names and "id_rsa" not in names


def test_auth_error_is_reported(monkeypatch, workspace, fake_api) -> None:  # type: ignore[no-untyped-def]
    with make_client(
        monkeypatch, workspace, ANTHROPIC_API_KEY="invalid-key", ANTHROPIC_BASE_URL=fake_api
    ) as c:
        events = chat(c, "hi")
        err = next(e for e in events if e["type"] == "error")
        assert err["code"] == "auth_failed"
        conv = c.get(f"/api/conversations/{events[0]['conversation_id']}").json()
        assert conv["messages"][1]["status"] == "error"


def test_unconfigured_provider(monkeypatch, workspace) -> None:  # type: ignore[no-untyped-def]
    with make_client(monkeypatch, workspace) as c:
        h = c.get("/api/health").json()
        assert h["provider"]["configured"] is False and h["provider"]["name"] == "unconfigured"
        r = c.post("/api/chat", json={"message": "hi"})
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "provider_not_configured"


def test_demo_mode_is_labeled_and_runs_no_tools(monkeypatch, workspace) -> None:  # type: ignore[no-untyped-def]
    with make_client(monkeypatch, workspace, NEXUS_PROVIDER="demo") as c:
        events = chat(c, "list my files")
        assert events[0]["demo"] is True
        assert not [e for e in events if e["type"].startswith("tool")]
        text = "".join(e.get("delta", "") for e in events)
        assert "Demo mode" in text and "no files were searched" in text
