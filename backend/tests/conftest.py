from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi.testclient import TestClient

from tests import fake_anthropic


def _make_pdf(text: str) -> bytes:
    """Build a minimal valid one-page PDF with a real text layer."""
    stream = f"BT /F1 18 Tf 20 70 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer << /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


PDF_BYTES = _make_pdf("NEXUS revision notes")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def serve_in_thread(asgi_app: Any) -> Iterator[str]:
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(asgi_app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("fake server did not start")
        time.sleep(0.02)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def fake_api() -> Iterator[str]:
    yield from serve_in_thread(fake_anthropic.app)


@pytest.fixture(scope="session")
def fake_ollama_url() -> Iterator[str]:
    from tests import fake_ollama

    yield from serve_in_thread(fake_ollama.app)


@pytest.fixture
def workspace(tmp_path: Path) -> dict[str, Path]:
    approved = tmp_path / "approved"
    (approved / "notes").mkdir(parents=True)
    (approved / "notes" / "physics.md").write_text("# Physics\nNewton's second law: F = ma\n")
    (approved / "lecture.pdf").write_bytes(PDF_BYTES)
    (approved / ".env").write_text("SECRET=hunter2\n")
    (approved / "id_rsa").write_text("PRIVATE KEY\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("top secret\n")
    (approved / "sneaky_link").symlink_to(outside)
    return {"root": tmp_path, "approved": approved, "outside": outside}


def make_client(
    monkeypatch: pytest.MonkeyPatch, workspace: dict[str, Path], **env: str
) -> TestClient:
    from app import config

    base = {
        "NEXUS_PROVIDER": "auto",
        "ANTHROPIC_API_KEY": "",
        "ANTHROPIC_AUTH_TOKEN": "",
        "ANTHROPIC_BASE_URL": "",
        "NEXUS_DB_PATH": str(workspace["root"] / "test.db"),
        "NEXUS_ALLOWED_DIRS": str(workspace["approved"]),
        "NEXUS_REFUSAL_FALLBACK": "true",
        "NEXUS_OLLAMA_URL": "http://127.0.0.1:9",
        "NEXUS_OLLAMA_MODEL": "fake-tools",
    }
    for k, v in {**base, **env}.items():
        monkeypatch.setenv(k, v)
    config.get_settings.cache_clear()
    from app.main import app

    return TestClient(app)


def read_sse(response: Any) -> list[dict[str, Any]]:
    events = []
    for line in response.iter_lines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events
