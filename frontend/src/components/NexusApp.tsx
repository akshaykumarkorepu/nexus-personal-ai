"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Menu } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { ToolInfo } from "@/lib/types";
import { useChat } from "@/lib/useChat";
import { useHealth } from "@/lib/useHealth";
import { cn } from "@/lib/utils";
import type { CoreState } from "./AICore";
import { ChatView } from "./ChatView";
import { FilesView } from "./FilesView";
import { RoadmapView } from "./RoadmapView";
import { SettingsView } from "./SettingsView";
import { Sidebar, type View } from "./Sidebar";
import { StatusRail } from "./StatusRail";

const TITLES: Record<View, string> = {
  chat: "Conversation",
  files: "Files",
  projects: "Projects",
  tasks: "Tasks",
  settings: "Settings",
};

export function NexusApp() {
  const chat = useChat();
  const { health, link, latency, error: healthError } = useHealth();
  const [view, setView] = useState<View>("chat");
  const [menuOpen, setMenuOpen] = useState(false);
  const [draft, setDraft] = useState<string | null>(null);
  const [tools, setTools] = useState<ToolInfo[]>([]);

  useEffect(() => {
    if (link !== "online") return;
    api
      .tools()
      .then((r) => setTools(r.tools))
      .catch(() => setTools([]));
  }, [link]);

  const coreState: CoreState = useMemo(() => {
    if (link === "offline") return "offline";
    const last = chat.messages[chat.messages.length - 1];
    if (chat.streaming) {
      const lastPart = last?.parts[last.parts.length - 1];
      return lastPart?.type === "text" ? "speaking" : "thinking";
    }
    if (last?.role === "assistant" && last.status === "error") return "error";
    return "idle";
  }, [chat.messages, chat.streaming, link]);

  const goto = useCallback((v: View) => {
    setView(v);
    setMenuOpen(false);
  }, []);

  const activeTitle =
    view === "chat"
      ? (chat.conversations.find((c) => c.id === chat.activeId)?.title ?? "New conversation")
      : TITLES[view];

  return (
    <div className="nexus-backdrop relative flex h-dvh overflow-hidden">
      <div className="nexus-grid pointer-events-none absolute inset-0" aria-hidden />

      <Sidebar
        view={view}
        onView={goto}
        conversations={chat.conversations}
        activeId={chat.activeId}
        onSelect={(id) => {
          void chat.select(id);
          goto("chat");
        }}
        onNew={() => {
          chat.newChat();
          goto("chat");
        }}
        onDelete={(id) => void chat.remove(id)}
        coreState={coreState}
        version={health?.version}
        listError={chat.listError}
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
      />

      <main className="relative flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line px-3 sm:px-5">
          <button
            type="button"
            onClick={() => setMenuOpen(true)}
            className="rounded-md p-1.5 text-ink-muted hover:text-ice lg:hidden"
            aria-label="Open menu"
          >
            <Menu className="size-5" />
          </button>
          <div className="min-w-0 flex-1">
            <div className="hud-label !text-[9px]">{TITLES[view]}</div>
            <div className="truncate text-sm text-ink">{activeTitle}</div>
          </div>
          <div className="flex items-center gap-2 font-mono text-[10px] tracking-wider">
            {health?.provider.demo && (
              <span className="rounded border border-warn/40 bg-warn/10 px-2 py-0.5 text-warn">DEMO MODE</span>
            )}
            <span
              className={cn(
                "flex items-center gap-1.5 rounded-full border px-2.5 py-1",
                link === "online" && health?.provider.configured && health.provider.ready !== false
                  ? "border-ok/30 text-ok"
                  : link === "offline"
                    ? "border-danger/30 text-danger"
                    : "border-warn/30 text-warn",
              )}
            >
              <span className="size-1.5 rounded-full bg-current shadow-[0_0_8px_currentColor]" />
              {link === "offline"
                ? "OFFLINE"
                : link === "checking"
                  ? "LINKING"
                  : !health?.provider.configured
                    ? "NO PROVIDER"
                    : health.provider.ready === false
                      ? "MODEL OFFLINE"
                      : health.provider.name === "ollama"
                        ? "ONLINE · LOCAL"
                        : "ONLINE"}
            </span>
          </div>
        </header>

        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={view}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.18 }}
            className="flex min-h-0 flex-1 flex-col"
          >
            {view === "chat" && (
              <ChatView
                messages={chat.messages}
                streaming={chat.streaming}
                loading={chat.loading}
                coreState={coreState}
                health={health}
                link={link}
                healthError={healthError}
                onSend={(text) => void chat.send(text)}
                onStop={chat.stop}
                draft={draft}
                onDraft={setDraft}
                onDraftConsumed={() => setDraft(null)}
              />
            )}
            {view === "files" && (
              <FilesView
                onAsk={(prompt) => {
                  chat.newChat();
                  setDraft(prompt);
                  goto("chat");
                }}
              />
            )}
            {view === "projects" && (
              <RoadmapView
                label="Projects"
                title="Code projects"
                intro="Inspect repositories, run approved development commands and tests, with every state-changing step gated behind your approval."
                tools={tools}
                items={[
                  { title: "Repository inspection", description: "Read project structure, git status and recent changes inside approved folders." },
                  { title: "Approved dev commands", description: "Run commands from an explicit allowlist (tests, lint, build) with timeouts and output limits. Never free-form shell.", tool: "run_dev_command" },
                  { title: "Test runner", description: "Run a project's test suite and summarize failures with links to the relevant files.", tool: "run_dev_command" },
                  { title: "File edits", description: "Propose changes as diffs that you approve before anything is written.", tool: "write_file" },
                ]}
              />
            )}
            {view === "tasks" && (
              <RoadmapView
                label="Tasks"
                title="Multi-step workflows"
                intro="Plans that run step by step with live progress, pausing for your confirmation before any action that changes state or leaves this machine."
                tools={tools}
                items={[
                  { title: "Workflow engine", description: "Break a goal into steps, track progress, and resume after interruptions." },
                  { title: "Approval gates", description: "Explicit confirmation before modifying files, running commands, submitting forms or other external actions." },
                  { title: "Browser automation", description: "Playwright-driven browsing to read pages and fill forms, with submission requiring approval.", tool: "browser" },
                  { title: "Voice conversation", description: "Hands-free spoken replies. Dictation into the chat box already works in supported browsers." },
                ]}
              />
            )}
            {view === "settings" && <SettingsView health={health} link={link} tools={tools} />}
          </motion.div>
        </AnimatePresence>
      </main>

      <StatusRail
        health={health}
        link={link}
        latency={latency}
        coreState={coreState}
        lastUsage={chat.lastUsage}
      />
    </div>
  );
}
