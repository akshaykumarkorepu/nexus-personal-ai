# NEXUS

**NEXUS is a privacy-conscious personal AI assistant that runs on your Mac and opens in your browser.** It pairs a sci-fi interface with a local Python backend. By default it talks to a **free local model through [Ollama](https://ollama.com)**, so no API key or usage cost is needed. Anthropic's Claude models can be switched on optionally.

It's built to grow step by step into a voice-enabled assistant that can work with your files, projects and tasks. Every new capability goes behind explicit permissions. See the [roadmap](docs/ROADMAP.md).

## What works today

- **Local AI chat** with streamed replies, using Ollama (default `qwen3:4b`). The Anthropic API is an optional alternative.
- **Persistent conversations** in a local SQLite database, restored after a reload or restart.
- **Stop** a reply mid-stream. The partial answer is kept and marked as stopped.
- **Read-only file tools** the model can call: list, search, and read text and PDF files inside folders you approve. Each call appears in the chat as a live activity card.
- **Files view** for browsing approved folders and asking NEXUS about a file. A PDF can be turned into a revision-notes request with one click.
- **Settings and status panels** for the provider, model, readiness, tool registry and token usage.
- **Dictation** into the input box using the browser's speech recognition.
- **Copy** buttons for whole responses and code blocks.

**Not built yet**, and labeled as such in the app: running commands or tests, browser automation, file writing, memory, tasks and reminders, and spoken replies. See [Known limitations](#known-limitations) and the [roadmap](docs/ROADMAP.md).

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (App Router), React 19, TypeScript (strict), Tailwind CSS 4, Lucide, Framer Motion, react-markdown |
| Backend | Python 3.12+, FastAPI, Pydantic v2, pydantic-settings, SQLite, httpx, pypdf |
| AI | Ollama (local, default) · Anthropic Python SDK (optional) |
| Quality | pytest, ruff, mypy (strict), ESLint, `tsc` |

---

## Architecture

```
Browser ──► Next.js (port 3000) ──/api/nexus/*──► FastAPI backend (port 8000) ──► Ollama (local, free)
            UI + same-origin proxy                 chat loop · tools · SQLite      or Anthropic API (optional)
```

- **`frontend/`**: Next.js 16 (App Router, TypeScript strict, Tailwind 4, Lucide, Framer Motion). The browser only talks to the Next.js server. A catch-all route handler (`src/app/api/nexus/[...path]/route.ts`) forwards an allowlisted set of paths to the backend and streams responses through unchanged. If the browser aborts a request, the upstream request is aborted too. No credentials exist in the frontend.
- **`backend/`**: FastAPI + Pydantic + SQLite.
  - `app/providers/`: provider abstraction. Adding a provider means implementing `stream_turn()`.
    - `OllamaProvider` streams from a local Ollama server's `/api/chat`. It translates the stored transcript to Ollama messages and back, so history, tools and cancellation work unchanged.
    - `AnthropicProvider` streams through the official Anthropic SDK.
    - `DemoProvider` is an explicitly labeled offline mode.
  - `app/chat.py`: the orchestrator. It streams text, runs requested tools through the registry, sends results back to the model, and loops up to `NEXUS_MAX_TOOL_ITERATIONS` times. Events reach the browser as server-sent events.
  - `app/tools/`: the **tool registry**. Each tool declares a name, description, Pydantic input schema, handler and permission level (`read_only`, `write`, `execute`, `external`).
  - `app/db.py`: SQLite. Each conversation keeps an append-only provider transcript (content blocks stored verbatim) next to the UI's render log. Earlier turns are never edited, which keeps replayed reasoning blocks valid and the prompt cache effective.

### Safety model

- The model can only call tools in the registry. Unknown tools and planned-but-unimplemented tools are refused.
- Every tool input is validated against its schema before anything runs. Extra fields are rejected.
- Tools that would modify files, run commands or act externally need explicit user approval. The approval UI doesn't exist yet, so those tools are **never offered to the model**, and the registry refuses them even if one is requested.
- File access is limited to the directories in `NEXUS_ALLOWED_DIRS`:
  - Paths are fully resolved, following symlinks, and must land inside an approved root. This blocks `..` traversal, absolute paths elsewhere, and symlinks that escape.
  - Sensitive names are always refused: `.env*`, `.ssh`, `.aws`, `.git`, `id_rsa*`, `*.pem`, `*.key`, keychains and similar.
  - Directory walks never follow symlinked directories.
- Every tool call has a timeout (`NEXUS_TOOL_TIMEOUT_SECONDS`). Output is capped at `NEXUS_MAX_READ_CHARS`, and file size at `NEXUS_MAX_FILE_BYTES`.
- There is no shell tool. The planned `run_dev_command` accepts only an ID from an allowlist and never free-form command text.
- The system prompt tells the model to treat file contents as data, not as instructions.
- Demo mode never calls a model and never emits tool events, so nothing can suggest real work was done.

---

## Setup

Requirements: macOS, Python 3.12+, Node 20+ (tested with Python 3.13 and Node 26).

### 1. Local model (Ollama, free)

Install Ollama, start it, and pull a tool-capable model:

```bash
brew install ollama
```
```bash
brew services start ollama
```
```bash
ollama pull qwen3:4b
```

Or install the Ollama app from https://ollama.com/download and open it instead of the first two commands. Check it's running with `ollama list`.

`qwen3:4b` (about 2.5 GB) runs comfortably on a 16 GB Mac. For better answers, try `qwen3:8b` (about 5 GB) and set `NEXUS_OLLAMA_MODEL=qwen3:8b`.

### 2. Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
[ -e .env ] || cp .env.example .env
```

In `backend/.env`:

```bash
NEXUS_PROVIDER=ollama
NEXUS_OLLAMA_MODEL=qwen3:4b
NEXUS_ALLOWED_DIRS=/Users/you/Documents/Notes,/Users/you/Study   # optional; absolute paths
```

To use Claude later instead, set `NEXUS_PROVIDER=auto` and add `ANTHROPIC_API_KEY`.

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local     # NEXUS_BACKEND_URL=http://127.0.0.1:8000
```

### 4. Run

Use two terminals:

```bash
cd backend && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
cd frontend && npm run dev
```

Open http://localhost:3000. If port 3000 is busy, run `npm run dev -- --port 3100` and add that origin to `NEXUS_CORS_ORIGINS`. That variable only matters if you call the backend directly; the proxy is same-origin.

For a production build: `cd frontend && npm run build && npm start`.

---

## Environment variables

### `backend/.env`

| Variable | Default | Purpose |
|---|---|---|
| `NEXUS_PROVIDER` | `auto` | `ollama` uses a local model with no key and no cost. `auto` uses Anthropic when credentials exist, otherwise reports "not configured". `demo` is the labeled offline mode. |
| `NEXUS_OLLAMA_MODEL` | `qwen3:4b` | Local model. Must be pulled, and should support tools for file access. |
| `NEXUS_OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama server. |
| `NEXUS_OLLAMA_NUM_CTX` | `16384` | Context window requested from Ollama (tokens). |
| `ANTHROPIC_API_KEY` | none | Anthropic API key. Read only by the backend. |
| `ANTHROPIC_AUTH_TOKEN` | none | OAuth bearer token, as an alternative to the key. |
| `ANTHROPIC_BASE_URL` | Anthropic | Override the API endpoint. |
| `NEXUS_MODEL` | `claude-opus-5-5` | Anthropic model ID. |
| `NEXUS_EFFORT` | `medium` | Anthropic reasoning depth: `low`, `medium`, `high`, `xhigh` or `max`. |
| `NEXUS_MAX_TOKENS` | `32000` | Per-reply output cap (includes reasoning). |
| `NEXUS_REFUSAL_FALLBACK` (Anthropic) | `true` | If a safety classifier declines, the API re-runs the request on Anthropic's recommended fallback model. |
| `NEXUS_ALLOWED_DIRS` | empty | Comma-separated absolute folders the file tools may read. Empty means no file access. |
| `NEXUS_DB_PATH` | `backend/data/nexus.db` | SQLite file. |
| `NEXUS_CORS_ORIGINS` | `http://localhost:3000` | Origins allowed to call the backend directly. |
| `NEXUS_MAX_TOOL_ITERATIONS` | `8` | Maximum tool round-trips per message. |
| `NEXUS_TOOL_TIMEOUT_SECONDS` | `10` | Per-tool timeout. |
| `NEXUS_MAX_READ_CHARS` | `60000` | Maximum characters a tool returns per call. The example file uses `20000` to fit a local model's context. |
| `NEXUS_MAX_FILE_BYTES` | 25 MB | Largest file `read_file` will open. |

### `frontend/.env.local`

| Variable | Default | Purpose |
|---|---|---|
| `NEXUS_BACKEND_URL` | `http://127.0.0.1:8000` | Where the Next.js server forwards API calls. Server-side only. |

---

## API

| Method & path | Purpose |
|---|---|
| `GET /api/health` | Status, provider configuration (never secrets), available tools |
| `POST /api/chat` | `{message, conversation_id?}` → SSE stream: `meta`, `status`, `text`, `tool_start`, `tool_end`, `notice`, `error`, `done` |
| `GET/POST /api/conversations` | List or create conversations |
| `GET/PATCH/DELETE /api/conversations/{id}` | Fetch with messages, rename, delete |
| `GET /api/tools` | Tool registry with permission levels and implemented/enabled flags |
| `GET /api/files/roots`, `GET /api/files/list?path=` | Read-only browsing of approved folders, with the same safeguards as the tools |

Errors are always `{"error": {"code", "message"}}`.

---

## Development checks

```bash
cd backend
.venv/bin/python -m pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy app
```

```bash
cd frontend
npm run lint && npm run typecheck && npm run build
```

The backend tests include `tests/fake_ollama.py`, which mirrors Ollama 0.32's streaming format (checked against a real `qwen3:4b`), and `tests/fake_anthropic.py`, a **test-only** stand-in for the Messages API that speaks the real streaming wire format. With it, the real SDK, the streaming loop, tool calls, history replay, stop and error paths are tested without an API key. To click through the UI against the fake server, run `python -m tests.fake_anthropic --port 8787` from `backend/`, then start the backend with `ANTHROPIC_API_KEY=fake-test-key ANTHROPIC_BASE_URL=http://127.0.0.1:8787`. Never point real use at it.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Header shows **OFFLINE** / "Cannot reach the NEXUS backend" | Start the backend, and check that `NEXUS_BACKEND_URL` in `frontend/.env.local` matches its host and port. |
| **NO PROVIDER** / "No AI provider is configured" | Set `NEXUS_PROVIDER=ollama` (free) or add `ANTHROPIC_API_KEY` in `backend/.env`, then restart the backend. |
| **MODEL OFFLINE** / "Ollama is not reachable" | Open the Ollama app or run `brew services start ollama`. Check with `ollama list`. |
| "model … is not installed" | `ollama pull <model>`, or point `NEXUS_OLLAMA_MODEL` at a model listed by `ollama list`. |
| "… can't call tools, so file access is off" | The model has no tool support. Use `qwen3:4b`, `qwen3:8b` or `llama3.1:8b`. |
| Local replies are slow to start | The first message loads the model into memory (several seconds). Reasoning models like qwen3 also think before answering, shown as REASONING. |
| A local model misreads a long file | Lower `NEXUS_MAX_READ_CHARS` or raise `NEXUS_OLLAMA_NUM_CTX` (more context uses more RAM). |
| "Anthropic rejected the credentials" | The key is wrong or revoked. Replace it and restart. |
| "Model … was not found" | Check `NEXUS_MODEL`. |
| Requests go to an unexpected endpoint | A shell-exported `ANTHROPIC_BASE_URL` overrides the default. Unset it or set it explicitly in `backend/.env`. |
| "No directories are approved for file access" | Add absolute paths to `NEXUS_ALLOWED_DIRS` and restart. Relative or missing paths are ignored. |
| A file you expect is "denied" | It matches a protected name (keys, `.env`, `.git` and so on) or sits behind a symlink that leaves the approved folder. |
| Microphone button is disabled | The browser has no Web Speech API (for example Firefox). Use Chrome or Safari. Chrome sends dictation audio to Google's speech service. |
| Port 3000 in use | `npm run dev -- --port 3100` |

---

## Known limitations

- **Not implemented yet:** running development commands, repository inspection and tests, browser automation (Playwright), file writes, multi-step workflows with approval gates, and spoken replies. Their tools are registered as *planned* and are never offered to the model. The Projects and Tasks screens are labeled roadmap placeholders.
- **No approval UI yet.** That's why every non-read-only tool stays disabled.
- **Voice is dictation only.** It uses the browser's speech recognition to fill the input box. There is no wake word and no text-to-speech.
- **PDFs:** text extraction only (pypdf). Scanned PDFs without a text layer return no text, and there's no OCR. Up to 50 pages per call.
- **Search** is a bounded substring scan (2 MB per file, about 20k files, time-limited), not an index.
- **Long conversations** replay their full history on every request. No compaction yet, so very long threads grow in cost and eventually hit the context limit.
- A conversation's system prompt (including the list of approved folders) is frozen when the conversation starts. Folder changes still take effect immediately for the tools themselves.
- A tool that times out is abandoned, but its worker thread finishes in the background.
- The Ollama provider was verified against a real local `qwen3:4b`, including tool calls. The Anthropic provider was verified against the fake Messages API server; a live Anthropic call still needs a key.
- Local models are much weaker than Claude. Small models sometimes pick the wrong tool, or answer without reading the file you meant.
- Ollama reasoning ("thinking") text is never shown or stored. Only the answer is.
- Switching providers mid-conversation works, but the new model sees only the text and tool history, not the previous model's reasoning.
- Single-user and local-only. There is no authentication, so don't expose port 3000 or 8000 to a network.

## Roadmap

Development continues in phases, each with its own acceptance criteria and tests:

1. Stabilization and reliable local AI (CI, migrations, context budget for local models)
2. Chat experience, user-controlled memory, settings, and the **approval flow**
3. File, document and project intelligence, including approved test runs
4. Voice input, spoken replies and a hands-free mode
5. Controlled browser and computer automation
6. Projects, tasks, reminders and workflows
7. Integrations through MCP
8. Personalization, evals, reliability and performance (ongoing)

Details, dependencies and the recommended order are in [docs/ROADMAP.md](docs/ROADMAP.md).

## License

Released under the [MIT License](LICENSE).
