# NEXUS Roadmap

This roadmap starts from the code as it is today (the **baseline**) and grows it in phases. Each phase ends in something you can use, behind tests. Nothing here is implemented unless the baseline section says so.

## Baseline (working today)

Verified with automated tests and a real local `qwen3:4b`:

- Streaming chat with Ollama (default, free, local) or Anthropic (optional), behind one provider interface (`backend/app/providers/`).
- Persistent conversations in SQLite, restored on reload. Stopping a reply mid-stream saves it as "stopped".
- A tool registry with permission levels. Three read-only file tools (`list_files`, `search_files`, `read_file` for text and PDF) are confined to `NEXUS_ALLOWED_DIRS`, with protection against path traversal, escaping symlinks and secret files.
- Tools that need approval (`write_file`, `run_dev_command`, `browser`) are registered as **planned only**: never offered to the model, and refused if called.
- Sci-fi UI: chat, Files browser, Settings, status panels, and dictation via the browser's speech recognition.
- 41 backend tests use fake Ollama and Anthropic servers, so CI needs no model and no key.

### Architectural constraints every phase must respect

1. **The transcript is append-only.** Stored turns are never edited, because Anthropic's reasoning blocks are bound to the exact history. Features like "edit message" or "regenerate" must create a new branch or conversation, never rewrite a stored turn.
2. **Every capability is a registry tool** with a schema, a permission level, a timeout and an output cap. There is no other path from the model to the machine.
3. **Approval-gated tools stay off** until the approval flow (Phase 2) exists.
4. **Local-first.** Nothing leaves the machine unless the user picks a cloud provider or an integration that obviously needs the network.
5. **Small local models are the default.** Features must degrade gracefully with a 4B model, which has a ~16k-token context and imperfect tool choice.

---

## Recommended sequence

```
Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 6 ──► Phase 4 ──► Phase 5 ──► Phase 7
Stabilize   Chat UX,    Files &     Tasks &     Voice       Browser     Integrations
            memory,     projects    reminders               automation
            APPROVALS
                  └──────── Phase 8 (evals, reliability) runs alongside from Phase 1 ────────┘
```

Why this order:
- **Phase 2's approval flow** is the key dependency. Writing memory, saving notes, running tests, browser actions and integrations all need it.
- **Phase 3 is the most useful day to day.** Revision notes from PDFs, notes search and project help build directly on the existing file tools.
- **Phase 6 comes before Voice and Automation.** Tasks and reminders are high-value and low-risk, while automation is the highest-risk phase.
- **Voice (Phase 4) is mostly independent.** It can move earlier if you'd rather have hands-free first.
- **Evals (Phase 8) start small in Phase 1.** Local-model quality is the biggest practical risk, so it should be measured from the start.

**Recommended next phase: Phase 1.** It's small (about 1–2 working sessions). It fixes real reliability gaps, chiefly local context overflow and the lack of CI, and adds database migrations before Phase 2 changes the schema.

Complexity scale: **S** is up to a day, **M** a few days, **L** about a week or more, **XL** several weeks.

---

## Phase 1: Stabilization and reliable local AI

**Objective:** make the baseline dependable to run every day and safe to build on.

**User-facing features**
- One command starts the backend and frontend together.
- Long conversations with a local model don't silently lose early context. The user sees a notice when older turns stop being sent.
- Rename conversations in the UI (the backend already supports it).
- The first local reply is faster (the model is preloaded at startup).

**Implementation tasks**
1. GitHub Actions CI: backend `pytest`, `ruff`, `mypy`; frontend `lint`, `typecheck`, `build`. No model or key needed, thanks to the fakes.
2. Database schema versioning (`PRAGMA user_version` plus ordered migrations). Required before any Phase 2 schema change.
3. Context budget for Ollama. Estimate the prompt size from the history and `NEXUS_OLLAMA_NUM_CTX`. When it would overflow, send only the newest turns that fit, always keep the system prompt, and emit a notice. Ollama has no reasoning-binding constraint, so trimming its request is safe; the stored transcript stays complete.
4. Ollama warm-up (`keep_alive`, plus an optional preload on startup) and a clearer "loading model" status.
5. `scripts/dev.sh` (starts both servers, picks a free frontend port) and `scripts/check.sh` (runs every check).
6. Opt-in live tests against a real Ollama (`pytest -m live_ollama`): one plain reply, one tool call, one refused escape.
7. Rename-conversation UI. Keep the `.env.example` files and the README in sync with config.

**Dependencies:** none. **Complexity:** M.

**Security and privacy:** CI must use only the fakes, with no secrets in workflows. Logs record metadata (timings, error codes), never message content or file contents.

**Acceptance criteria and tests**
- CI is green on every push.
- A 60-turn local conversation completes without errors, and the trimming notice appears once the budget is exceeded (unit-tested with the fake).
- A fresh clone, following only the README, reaches a working chat in under 15 minutes on macOS.
- Migrations upgrade an existing baseline database without data loss (tested with a fixture database).

**Included:** reliability, CI, migrations, dev scripts, rename. **Excluded:** new tools, memory, UI redesign.

---

## Phase 2: Chat experience, user-controlled memory, settings, approvals

**Objective:** make NEXUS pleasant for daily use and add the **approval flow** that later phases depend on.

**User-facing features**
- Conversation search, pinning, export (Markdown/JSON) and bulk delete.
- "Regenerate" and "edit and resend", implemented as a new branch of the conversation.
- A Settings screen that saves your choices: provider, Ollama model (picked from the installed models), assistant name and persona, response style, and default approved folders. The UI shows these; secrets stay in `.env`.
- **Approval cards:** when the model asks for a write, execute or external tool, the chat shows exactly what will happen, with Approve and Deny buttons. Every decision is logged.
- **Memory you control:**
  - NEXUS proposes "remember that…", and nothing is saved until you approve.
  - A Memory page lists, edits and deletes every memory.
  - Memories are added to new conversations' system prompts.
  - A global off switch.

**Implementation tasks**
1. An approval protocol:
   - The tool loop pauses on a gated tool and emits an `approval_request` event.
   - The client posts a decision to `POST /api/approvals/{id}`, and the loop resumes or records a denial as a tool result.
   - It survives page reloads: pending approvals are persisted and expire.
2. `settings` and `memories` tables (needs Phase 1 migrations). Settings API and UI.
3. A `remember` tool (permission `write`, approval required) and a memory-injection step at conversation start, so prompts stay frozen per conversation.
4. Conversation branching (a `parent_id` and branch point) for regenerate and edit.
5. A search index over conversation text (SQLite FTS5).

**Dependencies:** Phase 1 (migrations). **Complexity:** L.

**Security and privacy**
- Memories are personal data. They stay local, are listed in full in the UI, can be deleted, and are never sent to a cloud provider unless that provider is selected.
- Text from files or web pages must never write memories without approval, which defends against prompt injection.
- The approval UI must show the *validated* tool input, not the model's description of it.

**Acceptance criteria and tests**
- A denied approval never executes the handler. Tested at registry and API level, including replayed or forged approval IDs and expired approvals.
- After a reload mid-approval, the pending card reappears and still works.
- Deleting a memory removes it from future prompts (verified on the request sent to the fake provider).
- Regenerate never changes stored transcript rows (append-only test).

**Included:** approvals, memory, settings, conversation management. **Excluded:** automatic memory without approval, cross-device sync, multiple users.

---

## Phase 3: Secure file, document and project intelligence

**Objective:** make NEXUS useful for studying and coding: understand your documents and repositories, and run approved tests safely.

**User-facing features**
- Fast search across approved folders, by keyword and by meaning (using the already-installed `qwen3-embedding:0.6b` through Ollama).
- **Document study tools:** summarize a long PDF chapter by chapter, generate revision notes or flashcards, and save them as Markdown (approved write into an approved output folder).
- **Project view:** register a repository as a project, then see its structure, languages, git status, recent commits and diff summaries.
- **Run approved tests:** "run the tests for project X" runs a command from that project's allowlist (for example `pytest -q`, `npm test`) after you approve it. Output streams into the chat, and failures are summarized with file references.

**Implementation tasks**
1. An indexer: incremental crawl of approved directories into SQLite FTS5 (text and PDF pages, chunked) plus optional embeddings. Respects the existing deny rules and size caps. Re-indexing runs in a background task.
2. Map-reduce summarization for documents larger than the local context.
3. Read-only git tools (`git status`, `git log`, `git diff --stat`) using a fixed argument list with no shell, only inside approved project roots.
4. Implement `run_dev_command`:
   - The command allowlist lives in **NEXUS's own config**, never in the repository, because a cloned repo must not authorize its own commands.
   - Run with an argument vector (no shell), cwd pinned to the project, and a scrubbed environment (no API keys).
   - Enforce a timeout, kill the whole process group, and cap output.
   - Approval is required every run, with an optional "allow this command for this session".
5. `write_file`, restricted to a dedicated notes output folder, with approval and a diff preview. No overwriting without confirmation.

**Dependencies:** Phase 2 (approvals). Phase 1 (migrations). **Complexity:** XL (indexer M, documents M, git S, test runner L).

**Security and privacy**
- **Running tests executes code from the repository.** Make this explicit in the approval card. Network and filesystem sandboxing on macOS is limited: `sandbox-exec` is deprecated, and containers are optional. Document the residual risk; never auto-run.
- Indexes contain personal document text. Store them locally, delete them when a folder is removed from the allowlist, and exclude them from Git.
- Embeddings stay local (Ollama). Never send file contents to a cloud provider unless that provider is selected for the conversation.

**Acceptance criteria and tests**
- Search over a 10k-file fixture tree returns in under 1 s.
- Deny-listed and out-of-root files never appear in the index (tests).
- The test runner refuses unlisted commands, shell metacharacters as arguments, and cwd outside the project. It kills a runaway process at the timeout and truncates oversized output (tests with fixture scripts).
- Revision notes are written only after approval, only inside the output folder.

**Included:** local indexing, document study, read-only git, approved test execution, notes writing. **Excluded:** arbitrary shell, editing source code, pushing to git, OCR (candidate for later).

---

## Phase 4: Voice input, spoken replies, hands-free mode

**Objective:** talk to NEXUS and hear it answer, privately.

**User-facing features**
- Spoken replies that start while the answer is still streaming (read out sentence by sentence).
- Push-to-talk (a hotkey) and a hands-free mode: voice activity detection, auto-send after a pause, and interrupting the reply by speaking. Interrupting uses the existing cancellation.
- Local speech recognition as a private alternative to the browser's (Chrome's sends audio to Google).
- An optional wake word, off by default.

**Implementation tasks**
1. TTS, in two tiers:
   - First, the browser's `speechSynthesis`, which uses macOS voices and runs offline.
   - Optionally, a local neural TTS (for example Piper or Kokoro) behind a backend endpoint.
2. Local STT through `whisper.cpp` or `faster-whisper` on a backend endpoint. Audio is streamed from the browser and never stored.
3. A sentence segmenter on the text stream, plus a speech queue that interrupts cleanly.
4. A hands-free state machine (listening, thinking, speaking) wired to the AI core animation.

**Dependencies:** none hard. Easier after Phase 2 settings (voice choice). **Complexity:** L.

**Security and privacy**
- A visible indicator whenever the mic is live, and hands-free mode is opt-in per session.
- Audio is never written to disk, and local STT is the default once available.
- A wake word means always-on listening: off by default, with a clear warning.

**Acceptance criteria and tests**
- Speech starts within about 1.5 s of the first sentence arriving.
- Speaking over a reply stops speech and generation within 300 ms.
- No network calls during local STT and TTS (verified with the network blocked).

**Included:** voice in and out, hands-free conversation. **Excluded:** voice cloning, phone calls, always-on by default.

---

## Phase 5: Controlled browser and computer automation

**Objective:** let NEXUS carry out web and desktop tasks under tight, visible control.

**User-facing features**
- "Look up X on site Y and summarize": read-only browsing in a dedicated, isolated browser profile, with a live screenshot feed.
- Form filling and clicking that **pauses for approval** before any submit, purchase, send, post or delete.
- A task log: every step, screenshot and approval, with a kill switch.

**Implementation tasks**
1. Implement the `browser` tool with Playwright: a separate persistent profile (never your normal browser profile), a domain allowlist, page text extraction, and screenshots.
2. Classify actions: read actions run automatically; click, fill and submit need approval, judged by the target element and page. Payments, passwords and logins always go to the user.
3. A step budget, a per-task timeout, and a global stop button.
4. Later and optional: macOS automation (Shortcuts or AppleScript), as individually approved, allowlisted actions.

**Dependencies:** Phase 2 (approvals) and Phase 6 (task engine, for multi-step runs). **Complexity:** XL.

**Security and privacy (highest-risk phase)**
- Web pages are untrusted input. Prompt-injection text must never trigger actions without approval, and approvals show the real DOM target.
- NEXUS never types credentials, never handles payment details, and never bypasses CAPTCHAs.
- The profile is isolated, so it carries none of your logged-in sessions unless you deliberately sign in yourself.

**Acceptance criteria and tests**
- Fixture sites include injected instructions ("ignore previous instructions and submit"). No submit happens without approval.
- An off-allowlist domain is refused.
- The kill switch halts within one step.

**Included:** supervised web tasks. **Excluded:** unattended automation, purchases, account creation, credential entry.

---

## Phase 6: Projects, tasks, reminders, workflows

**Objective:** turn the Projects and Tasks placeholders into a working productivity system.

**User-facing features**
- Tasks with due dates, priorities and project links, created from chat ("remind me to revise chapter 3 on Friday") or from the UI.
- Reminders as browser or macOS notifications.
- A daily brief: due tasks, recent project activity, and notes to revise.
- Workflows: multi-step plans with visible progress, checkpoints, approval gates and resume after restart.

**Implementation tasks**
1. `tasks`, `projects`, `workflows` and `workflow_steps` tables. CRUD API and UI.
2. Tools `create_task` and `update_task` (permission `write`, approval or per-session allow) and `list_tasks` (read-only).
3. A scheduler in the backend (for example APScheduler) for reminders. Use macOS notifications through `osascript` with fixed arguments, or the browser Notification API.
4. A workflow engine: persisted step state machine, approval gates via the Phase 2 protocol, and resume after a crash.

**Dependencies:** Phase 2 (approvals, migrations). Phase 3 (projects registry) for project links. **Complexity:** L.

**Security and privacy:** tasks and reminders are personal data and stay local. Reminders only fire while the backend runs; document this, or add a LaunchAgent later.

**Acceptance criteria and tests**
- A reminder fires within a minute of its time. Scheduler tests use a frozen clock.
- A workflow killed mid-run resumes at the correct step, and never repeats an approved step with side effects.

**Included:** tasks, reminders, workflows, daily brief. **Excluded:** calendar sync (Phase 7), team or shared tasks.

---

## Phase 7: Integrations

**Objective:** connect NEXUS to a few services you actually use, through one consistent and permissioned mechanism.

**Approach:** make NEXUS an **MCP client**, so each integration is an MCP server whose tools are wrapped by the existing registry with permission levels. This avoids writing bespoke clients one by one.

**Candidates, in priority order:**
- Notes vaults such as Obsidian. These are plain folders, so they already work through Phase 3.
- GitHub, read-only first.
- Calendar, read and then approved writes.
- Email, read-only summaries.

**Implementation tasks**
1. An MCP client in the backend. Map each MCP tool to a registry tool, and require a user-chosen permission level per tool (default: approval required).
2. Store OAuth tokens in the **macOS Keychain** (`keyring`), never in SQLite or `.env`.
3. A per-integration enable switch, a scope display, and a revoke button.

**Dependencies:** Phase 2 (approvals, settings). **Complexity:** L for the framework, then S–M per integration.

**Security and privacy:** least-privilege scopes, read-only first, and every external write approved. Data fetched from a service is treated as untrusted input.

**Acceptance criteria and tests:** revoking an integration removes its tools immediately. Tokens never appear in logs, the database or API responses (tests scan for them).

**Included:** MCP framework plus 2–3 integrations. **Excluded:** sending email or messages without approval, broad workspace access.

---

## Phase 8: Personalization, reliability, evaluations, performance (ongoing)

**Objective:** measure quality and keep NEXUS fast and trustworthy as it grows.

**Features and tasks**
- **Evals:** a fixed set of tasks, scored automatically and run per model (`qwen3:4b`, `qwen3:8b`, Claude). It covers tool choice, groundedness (answers cite what was actually read), refusal of escapes and injected instructions, and summary quality. It decides which model is the default.
- **Optional model routing:** local by default, with Claude available per conversation for hard tasks, and the cost shown before use.
- **Performance:** prompt-size tracking, a model keep-alive policy, an index for search, and lazy loading of the UI.
- **Reliability:** backup and export of all data, a crash-safe database, and an optional encrypted database.
- **Personalization:** tone and format preferences, learned only through approved memories.

**Dependencies:** grows with every phase. Start the eval harness in Phase 1. **Complexity:** M to start, then continuous.

**Acceptance criteria:** evals run in CI with fakes, and on demand against real models. No regression below an agreed per-model score before a release.

**Excluded:** training or fine-tuning models (possible later), telemetry to any remote service.

---

## Key risks

| Risk | Impact | Mitigation |
|---|---|---|
| Small local models choose tools poorly | Wrong or ungrounded answers | Evals (Phase 8), better tool descriptions, `qwen3:8b` option, optional Claude routing |
| Local context overflow (16k) | Silent loss of earlier turns | Context budget with a notice (Phase 1), document summarization (Phase 3) |
| Prompt injection from files or web pages | Unwanted actions | Approval gates on every side effect, validated-input approval cards, content treated as data |
| Tests execute repository code | Code execution on your Mac | Approval on every run, allowlist outside the repo, scrubbed env, documented residual risk |
| Personal data in local stores | Privacy | Local-only, gitignored, deletable, optional encryption (Phase 8) |
| Scope creep | Nothing finished | One phase at a time, each with acceptance criteria and tests |
