from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.tools import PermissionLevel, Tool, ToolContext, ToolError, ToolOutput, build_registry
from app.tools.paths import resolve_allowed


def ctx(roots: list[Path], **kw: object) -> ToolContext:
    base: dict[str, object] = {
        "roots": roots,
        "max_read_chars": 20_000,
        "max_file_bytes": 10_000_000,
        "timeout_seconds": 5.0,
    }
    base.update(kw)
    return ToolContext(**base)  # type: ignore[arg-type]


def run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


# --- path safeguards -----------------------------------------------------------


def test_allows_file_inside_root(workspace: dict[str, Path]) -> None:
    root = workspace["approved"].resolve()
    p = resolve_allowed(str(root / "notes" / "physics.md"), [root], expect="file")
    assert p.name == "physics.md"


def test_relative_path_with_single_root(workspace: dict[str, Path]) -> None:
    root = workspace["approved"].resolve()
    assert resolve_allowed("notes/physics.md", [root]).name == "physics.md"


@pytest.mark.parametrize(
    "raw",
    ["../outside/secret.txt", "notes/../../outside/secret.txt", "/etc/passwd", "~/.zshrc"],
)
def test_rejects_paths_outside_roots(workspace: dict[str, Path], raw: str) -> None:
    root = workspace["approved"].resolve()
    with pytest.raises(ToolError) as exc:
        resolve_allowed(raw, [root])
    assert exc.value.code in {"path_not_allowed", "not_found"}


def test_rejects_symlink_escape(workspace: dict[str, Path]) -> None:
    root = workspace["approved"].resolve()
    with pytest.raises(ToolError) as exc:
        resolve_allowed("sneaky_link/secret.txt", [root])
    assert exc.value.code == "path_not_allowed"


@pytest.mark.parametrize("name", [".env", "id_rsa"])
def test_rejects_sensitive_names(workspace: dict[str, Path], name: str) -> None:
    root = workspace["approved"].resolve()
    with pytest.raises(ToolError) as exc:
        resolve_allowed(name, [root])
    assert exc.value.code == "path_denied"


def test_no_roots_configured() -> None:
    with pytest.raises(ToolError) as exc:
        resolve_allowed("/tmp", [])
    assert exc.value.code == "no_approved_dirs"


def test_null_byte_rejected(workspace: dict[str, Path]) -> None:
    with pytest.raises(ToolError):
        resolve_allowed("notes/\x00physics.md", [workspace["approved"].resolve()])


# --- registry --------------------------------------------------------------------


def test_only_read_only_implemented_tools_are_offered() -> None:
    reg = build_registry()
    names = {t["name"] for t in reg.api_definitions()}
    assert names == {"list_files", "search_files", "read_file"}
    assert {"run_dev_command", "browser", "write_file"} <= set(reg.tools)


def test_planned_tool_is_refused(workspace: dict[str, Path]) -> None:
    reg = build_registry()
    res = run(reg.execute("run_dev_command", {"command_id": "rm", "project": "/"}, ctx([])))
    assert not res.ok and res.error_code == "not_implemented"


def test_unknown_tool_is_refused() -> None:
    res = run(build_registry().execute("bash", {"cmd": "ls"}, ctx([])))
    assert not res.ok and res.error_code == "unknown_tool"


def test_invalid_input_is_refused(workspace: dict[str, Path]) -> None:
    reg = build_registry()
    root = workspace["approved"].resolve()
    res = run(reg.execute("read_file", {"path": "x", "rm_rf": True}, ctx([root])))
    assert res.error_code == "invalid_input"
    res = run(reg.execute("read_file", "notes/physics.md", ctx([root])))
    assert res.error_code == "invalid_input"


class _Empty(BaseModel):
    pass


def test_approval_required_for_state_changing_tools() -> None:
    async def handler(args: _Empty, c: ToolContext) -> ToolOutput:
        raise AssertionError("must not run")

    reg = build_registry()
    reg.register(Tool("danger", "x", _Empty, PermissionLevel.WRITE, handler))
    assert "danger" not in {t["name"] for t in reg.api_definitions()}
    res = run(reg.execute("danger", {}, ctx([])))
    assert res.error_code == "approval_required"


def test_timeout_and_output_cap() -> None:
    async def slow(args: _Empty, c: ToolContext) -> ToolOutput:
        await asyncio.sleep(5)
        return ToolOutput("x", "x")

    async def big(args: _Empty, c: ToolContext) -> ToolOutput:
        return ToolOutput("y" * 50_000, "big")

    reg = build_registry()
    reg.register(Tool("slow", "x", _Empty, PermissionLevel.READ_ONLY, slow))
    reg.register(Tool("big", "x", _Empty, PermissionLevel.READ_ONLY, big))
    assert run(reg.execute("slow", {}, ctx([], timeout_seconds=0.1))).error_code == "timeout"
    res = run(reg.execute("big", {}, ctx([], max_read_chars=1000)))
    assert res.ok and len(res.content) < 1100 and "truncated" in res.content


# --- file tools ----------------------------------------------------------------------


def test_list_files_hides_sensitive_entries(workspace: dict[str, Path]) -> None:
    root = workspace["approved"].resolve()
    res = run(build_registry().execute("list_files", {"path": str(root), "depth": 2}, ctx([root])))
    assert res.ok
    assert "physics.md" in res.content and "lecture.pdf" in res.content
    assert ".env" not in res.content and "id_rsa" not in res.content
    assert "secret.txt" not in res.content  # symlink target outside root is not followed


def test_search_finds_content(workspace: dict[str, Path]) -> None:
    root = workspace["approved"].resolve()
    res = run(build_registry().execute("search_files", {"query": "newton"}, ctx([root])))
    assert res.ok and "physics.md" in res.content and "L2:" in res.content
    res = run(build_registry().execute("search_files", {"query": "hunter2"}, ctx([root])))
    assert "No matches" in res.content  # .env is never searched
    res = run(build_registry().execute("search_files", {"query": "top secret"}, ctx([root])))
    assert "No matches" in res.content  # nor files behind an escaping symlink


def test_read_text_and_pdf(workspace: dict[str, Path]) -> None:
    root = workspace["approved"].resolve()
    reg = build_registry()
    res = run(reg.execute("read_file", {"path": "notes/physics.md"}, ctx([root])))
    assert res.ok and "F = ma" in res.content
    res = run(reg.execute("read_file", {"path": "lecture.pdf"}, ctx([root])))
    assert res.ok, res.content
    assert "NEXUS revision notes" in res.content and "1 pages" in res.content


def test_read_refuses_secrets_and_escapes(workspace: dict[str, Path]) -> None:
    root = workspace["approved"].resolve()
    reg = build_registry()
    for path, code in [
        (".env", "path_denied"),
        ("../outside/secret.txt", "path_not_allowed"),
        ("sneaky_link/secret.txt", "path_not_allowed"),
        (str(workspace["outside"] / "secret.txt"), "path_not_allowed"),
    ]:
        res = run(reg.execute("read_file", {"path": path}, ctx([root])))
        assert not res.ok and res.error_code == code, (path, res)
        assert "hunter2" not in res.content and "top secret" not in res.content


def test_read_refuses_binary_and_large(workspace: dict[str, Path]) -> None:
    root = workspace["approved"].resolve()
    (root / "blob.txt").write_bytes(b"\x00\x01\x02" * 100)
    (root / "image.png").write_bytes(b"\x89PNG")
    reg = build_registry()
    assert (
        run(reg.execute("read_file", {"path": "blob.txt"}, ctx([root]))).error_code == "unsupported"
    )
    assert (
        run(reg.execute("read_file", {"path": "image.png"}, ctx([root]))).error_code
        == "unsupported"
    )
    res = run(reg.execute("read_file", {"path": "notes/physics.md"}, ctx([root], max_file_bytes=5)))
    assert res.error_code == "too_large"
