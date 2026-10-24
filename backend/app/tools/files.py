"""Read-only file tools: list, search and read inside approved directories."""

from __future__ import annotations

import asyncio
import fnmatch
import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .paths import SKIP_DIRS, display_path, is_denied_name, resolve_allowed, within_roots
from .registry import PermissionLevel, Tool, ToolContext, ToolError, ToolOutput

TEXT_EXTENSIONS = frozenset(
    [
        ".txt",
        ".md",
        ".markdown",
        ".rst",
        ".org",
        ".tex",
        ".csv",
        ".tsv",
        ".json",
        ".jsonl",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".xml",
        ".html",
        ".htm",
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
        ".vue",
        ".svelte",
        ".py",
        ".pyi",
        ".ipynb",
        ".rb",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".kts",
        ".scala",
        ".swift",
        ".m",
        ".mm",
        ".c",
        ".h",
        ".cc",
        ".cpp",
        ".hpp",
        ".cs",
        ".php",
        ".pl",
        ".lua",
        ".r",
        ".jl",
        ".dart",
        ".ex",
        ".exs",
        ".erl",
        ".hs",
        ".clj",
        ".sql",
        ".graphql",
        ".proto",
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".ps1",
        ".bat",
        ".gradle",
        ".properties",
        ".lock",
        ".log",
        ".env.example",
        ".gitignore",
        ".dockerignore",
        ".editorconfig",
        ".srt",
        ".vtt",
        ".bib",
    ]
)
TEXT_FILENAMES = frozenset(
    {"Makefile", "Dockerfile", "README", "LICENSE", "CHANGELOG", "Procfile", "Gemfile"}
)
PDF_MAX_PAGES_PER_CALL = 50
SEARCH_MAX_FILE_BYTES = 2 * 1024 * 1024
SEARCH_MAX_FILES_SCANNED = 20_000


def kind_of(path: Path) -> Literal["text", "pdf", "other"]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in TEXT_EXTENSIONS or path.name in TEXT_FILENAMES:
        return "text"
    return "other"


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds")


def _human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


def _walk(
    start: Path, roots: list[Path], max_depth: int, deadline: float
) -> Iterator[tuple[Path, os.DirEntry[str], int]]:
    """Breadth-first walk that never follows directory symlinks out of the roots."""
    queue: list[tuple[Path, int]] = [(start, 0)]
    while queue:
        directory, depth = queue.pop(0)
        if time.monotonic() > deadline:
            return
        try:
            with os.scandir(directory) as it:
                entries = sorted(it, key=lambda e: e.name.lower())
        except OSError:
            continue
        for entry in entries:
            if is_denied_name(entry.name):
                continue
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if entry.is_symlink():
                try:
                    target = Path(entry.path).resolve(strict=True)
                except OSError:
                    continue
                if not within_roots(target, roots):
                    continue
                is_dir = False  # report symlinks but never descend through them
            yield Path(entry.path), entry, depth
            if is_dir and entry.name not in SKIP_DIRS and depth + 1 < max_depth:
                queue.append((Path(entry.path), depth + 1))


# --- list_files ---------------------------------------------------------------


class ListFilesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str | None = Field(
        None,
        description="Directory to list. Omit to list the approved root directories.",
        max_length=4096,
    )
    depth: int = Field(1, ge=1, le=4, description="How many directory levels to include.")
    max_entries: int = Field(200, ge=1, le=1000)


def _list_files(args: ListFilesInput, ctx: ToolContext) -> ToolOutput:
    if args.path is None:
        if not ctx.roots:
            raise ToolError("No directories are approved for file access.", "no_approved_dirs")
        listing = ["Approved directories:"] + [f"- {r}" for r in ctx.roots]
        return ToolOutput("\n".join(listing), f"Listed {len(ctx.roots)} approved directories")

    base = resolve_allowed(args.path, ctx.roots, expect="dir")
    deadline = time.monotonic() + ctx.timeout_seconds * 0.8
    lines: list[str] = []
    truncated = False
    for path, entry, depth in _walk(base, ctx.roots, args.depth, deadline):
        if len(lines) >= args.max_entries:
            truncated = True
            break
        indent = "  " * depth
        rel = path.name
        try:
            st = entry.stat(follow_symlinks=False)
        except OSError:
            continue
        if entry.is_dir(follow_symlinks=False):
            lines.append(f"{indent}{rel}/")
        else:
            lines.append(
                f"{indent}{rel}  ({_human_size(st.st_size)}, modified {_iso(st.st_mtime)})"
            )
    header = f"Contents of {base}" + (f" (depth {args.depth})" if args.depth > 1 else "")
    body = "\n".join(lines) if lines else "(empty)"
    if truncated:
        body += f"\n[Stopped after {args.max_entries} entries.]"
    return ToolOutput(f"{header}\n{body}", f"Listed {len(lines)} entries in {display_path(base)}")


async def list_files(args: ListFilesInput, ctx: ToolContext) -> ToolOutput:
    return await asyncio.to_thread(_list_files, args, ctx)


# --- search_files -------------------------------------------------------------


class SearchFilesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(
        ..., min_length=1, max_length=200, description="Text to look for (case-insensitive)."
    )
    path: str | None = Field(
        None,
        description="Directory to search. Omit to search every approved directory.",
        max_length=4096,
    )
    mode: Literal["name", "content", "both"] = Field(
        "both", description="Match file names, text file contents, or both."
    )
    glob: str | None = Field(
        None, max_length=100, description="Optional file-name filter such as '*.md'."
    )
    max_results: int = Field(50, ge=1, le=200)


def _search_files(args: SearchFilesInput, ctx: ToolContext) -> ToolOutput:
    bases = [resolve_allowed(args.path, ctx.roots, expect="dir")] if args.path else list(ctx.roots)
    if not bases:
        raise ToolError("No directories are approved for file access.", "no_approved_dirs")
    needle = args.query.lower()
    deadline = time.monotonic() + ctx.timeout_seconds * 0.8
    results: list[str] = []
    scanned = 0
    timed_out = False

    for base in bases:
        for path, entry, _depth in _walk(base, ctx.roots, 12, deadline):
            if len(results) >= args.max_results:
                break
            if time.monotonic() > deadline:
                timed_out = True
                break
            try:
                if not entry.is_file():
                    continue
            except OSError:
                continue
            if args.glob and not fnmatch.fnmatch(entry.name, args.glob):
                continue
            scanned += 1
            if scanned > SEARCH_MAX_FILES_SCANNED:
                timed_out = True
                break
            name_hit = args.mode in ("name", "both") and needle in entry.name.lower()
            snippets: list[str] = []
            if args.mode in ("content", "both") and kind_of(path) == "text":
                try:
                    if entry.stat().st_size <= SEARCH_MAX_FILE_BYTES:
                        with open(path, encoding="utf-8", errors="replace") as fh:
                            for lineno, line in enumerate(fh, 1):
                                if needle in line.lower():
                                    snippets.append(f"    L{lineno}: {line.strip()[:200]}")
                                    if len(snippets) >= 3:
                                        break
                except OSError:
                    pass
            if name_hit or snippets:
                results.append(str(path) + (" (name match)" if name_hit else ""))
                results.extend(snippets)
                if len(results) >= args.max_results * 4:
                    break

    file_hits = sum(1 for r in results if not r.startswith("    "))
    header = f'Search for "{args.query}" ({args.mode}) - {file_hits} matching files'
    notes = []
    if timed_out:
        notes.append("[Search stopped early: time or file-count limit reached.]")
    body = "\n".join(results) if results else "No matches."
    return ToolOutput(
        "\n".join([header, body, *notes]),
        f'Found {file_hits} files matching "{args.query}"',
    )


async def search_files(args: SearchFilesInput, ctx: ToolContext) -> ToolOutput:
    return await asyncio.to_thread(_search_files, args, ctx)


# --- read_file ----------------------------------------------------------------


class ReadFileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(..., min_length=1, max_length=4096, description="File to read.")
    start_line: int = Field(1, ge=1, description="Text files: first line to return (1-based).")
    start_page: int = Field(1, ge=1, description="PDFs: first page to return (1-based).")
    end_page: int | None = Field(
        None, ge=1, description=f"PDFs: last page (at most {PDF_MAX_PAGES_PER_CALL} per call)."
    )


def _read_text(path: Path, args: ReadFileInput, ctx: ToolContext) -> ToolOutput:
    with open(path, "rb") as fh:
        head = fh.read(8192)
    if b"\x00" in head:
        raise ToolError("File looks binary; only text and PDF files can be read.", "unsupported")
    out: list[str] = []
    used = 0
    last_line = args.start_line - 1
    truncated = False
    with open(path, encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            if lineno < args.start_line:
                continue
            numbered = f"{lineno:>6}  {line.rstrip()}"
            if used + len(numbered) + 1 > ctx.max_read_chars:
                truncated = True
                break
            out.append(numbered)
            used += len(numbered) + 1
            last_line = lineno
    header = f"File: {path} (lines {args.start_line}-{last_line})"
    footer = (
        f"\n[Truncated. Call read_file again with start_line={last_line + 1} to continue.]"
        if truncated
        else ""
    )
    body = "\n".join(out) if out else "(no content at or after this line)"
    return ToolOutput(f"{header}\n{body}{footer}", f"Read {display_path(path)}")


def _read_pdf(path: Path, args: ReadFileInput, ctx: ToolContext) -> ToolOutput:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise ToolError("PDF is encrypted.", "unsupported")
        total = len(reader.pages)
    except PdfReadError as exc:
        raise ToolError(f"Could not parse PDF: {exc}", "unsupported") from None
    if args.start_page > total:
        raise ToolError(f"PDF has only {total} pages.", "invalid_input")
    end = min(args.end_page or total, total, args.start_page + PDF_MAX_PAGES_PER_CALL - 1)
    if end < args.start_page:
        raise ToolError("end_page must be >= start_page.", "invalid_input")
    parts: list[str] = []
    used = 0
    last = args.start_page - 1
    for i in range(args.start_page - 1, end):
        text = (reader.pages[i].extract_text() or "").strip()
        chunk = f"--- Page {i + 1} ---\n{text or '(no extractable text; may be scanned)'}"
        if used + len(chunk) > ctx.max_read_chars and parts:
            break
        parts.append(chunk)
        used += len(chunk)
        last = i + 1
    header = f"PDF: {path} ({total} pages; showing {args.start_page}-{last})"
    footer = (
        f"\n[More pages remain. Call read_file with start_page={last + 1} to continue.]"
        if last < total
        else ""
    )
    return ToolOutput(
        f"{header}\n" + "\n\n".join(parts) + footer,
        f"Read {display_path(path)} pages {args.start_page}-{last} of {total}",
    )


def _read_file(args: ReadFileInput, ctx: ToolContext) -> ToolOutput:
    path = resolve_allowed(args.path, ctx.roots, expect="file")
    size = path.stat().st_size
    if size > ctx.max_file_bytes:
        raise ToolError(
            f"File is {_human_size(size)}; the limit is {_human_size(ctx.max_file_bytes)}.",
            "too_large",
        )
    kind = kind_of(path)
    if kind == "pdf":
        return _read_pdf(path, args, ctx)
    if kind == "text":
        return _read_text(path, args, ctx)
    raise ToolError(
        f"Unsupported file type '{path.suffix or path.name}'. Text and PDF files are supported.",
        "unsupported",
    )


async def read_file(args: ReadFileInput, ctx: ToolContext) -> ToolOutput:
    return await asyncio.to_thread(_read_file, args, ctx)


FILE_TOOLS = [
    Tool(
        name="list_files",
        description=(
            "List files and folders inside the user's approved directories. Call with no "
            "path to see which directories are approved. Read-only."
        ),
        input_model=ListFilesInput,
        permission=PermissionLevel.READ_ONLY,
        handler=list_files,
        category="files",
    ),
    Tool(
        name="search_files",
        description=(
            "Search file names and text file contents inside the approved directories. "
            "Returns matching paths with up to three matching lines each. Read-only."
        ),
        input_model=SearchFilesInput,
        permission=PermissionLevel.READ_ONLY,
        handler=search_files,
        category="files",
    ),
    Tool(
        name="read_file",
        description=(
            "Read a text file (with line numbers) or extract text from a PDF inside the "
            "approved directories. Long files are returned in pages; follow the "
            "continuation hint to read more. Read-only."
        ),
        input_model=ReadFileInput,
        permission=PermissionLevel.READ_ONLY,
        handler=read_file,
        category="files",
    ),
]


def list_directory(raw: str, roots: list[Path]) -> tuple[Path, list[dict[str, object]]]:
    """Structured, single-level listing for the Files view (same safeguards as the tools)."""
    base = resolve_allowed(raw, roots, expect="dir")
    entries: list[dict[str, object]] = []
    deadline = time.monotonic() + 5
    for path, entry, _depth in _walk(base, roots, 1, deadline):
        if len(entries) >= 1000:
            break
        try:
            st = entry.stat(follow_symlinks=False)
            is_link = entry.is_symlink()
            is_dir = entry.is_dir(follow_symlinks=False)
        except OSError:
            continue
        kind = "symlink" if is_link else "dir" if is_dir else "file"
        entries.append(
            {
                "name": entry.name,
                "path": str(path),
                "type": kind,
                "size": None if is_dir else st.st_size,
                "modified": _iso(st.st_mtime),
                "readable": kind == "file" and kind_of(path) != "other",
            }
        )
    entries.sort(key=lambda e: (e["type"] != "dir", str(e["name"]).lower()))
    return base, entries
