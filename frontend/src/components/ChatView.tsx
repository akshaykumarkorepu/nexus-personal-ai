"use client";

import { motion } from "framer-motion";
import { FileSearch, FolderTree, KeyRound, NotebookPen, Sparkles, TriangleAlert } from "lucide-react";
import { useEffect, useRef } from "react";
import type { ChatMessage, Health } from "@/lib/types";
import type { LinkState } from "@/lib/useHealth";
import { AICore, type CoreState } from "./AICore";
import { Composer } from "./Composer";
import { MessageView } from "./MessageView";

const SUGGESTIONS = [
  { icon: Sparkles, text: "What can you do for me right now?" },
  { icon: FolderTree, text: "Which folders can you access?" },
  { icon: FileSearch, text: "Search my files for notes about " },
  { icon: NotebookPen, text: "Create revision notes from the PDF at " },
];

function greeting(): string {
  const h = new Date().getHours();
  return h < 5 ? "Working late" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

function SetupCard({ health, link, error }: { health: Health | null; link: LinkState; error: string | null }) {
  if (link === "offline") {
    return (
      <div className="panel brackets mx-auto mt-6 max-w-lg rounded-xl p-4 text-sm">
        <div className="mb-1 flex items-center gap-2 text-danger">
          <TriangleAlert className="size-4" /> Backend offline
        </div>
        <p className="text-ink-muted">{error}</p>
        <p className="mt-2 font-mono text-xs text-ink-faint">
          cd backend && .venv/bin/uvicorn app.main:app --port 8000
        </p>
      </div>
    );
  }
  if (health && !health.provider.configured) {
    return (
      <div className="panel brackets mx-auto mt-6 max-w-lg rounded-xl p-4 text-sm">
        <div className="mb-1 flex items-center gap-2 text-warn">
          <KeyRound className="size-4" /> AI provider not configured
        </div>
        <p className="text-ink-muted">{health.provider.message}</p>
      </div>
    );
  }
  if (health?.provider.ready === false) {
    return (
      <div className="panel brackets mx-auto mt-6 max-w-lg rounded-xl p-4 text-sm">
        <div className="mb-1 flex items-center gap-2 text-warn">
          <TriangleAlert className="size-4" /> Local model not ready
        </div>
        <p className="text-ink-muted">{health.provider.message}</p>
      </div>
    );
  }
  if (health?.provider.demo) {
    return (
      <div className="mx-auto mt-6 max-w-lg rounded-xl border border-warn/30 bg-warn/5 p-3 text-center text-xs text-warn">
        Demo mode: replies are canned text. No model is called and no tools run.
      </div>
    );
  }
  return null;
}

export function ChatView({
  messages,
  streaming,
  loading,
  coreState,
  health,
  link,
  healthError,
  onSend,
  onStop,
  draft,
  onDraft,
  onDraftConsumed,
}: {
  messages: ChatMessage[];
  streaming: boolean;
  loading: boolean;
  coreState: CoreState;
  health: Health | null;
  link: LinkState;
  healthError: string | null;
  onSend: (text: string) => void;
  onStop: () => void;
  draft: string | null;
  /** Pre-fill the composer (for prompts the user should finish). */
  onDraft: (text: string) => void;
  onDraftConsumed: () => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);

  // Follow the stream unless the user has scrolled up to read.
  useEffect(() => {
    const el = scrollRef.current;
    if (el && pinnedRef.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const unavailable = link === "offline" || (health !== null && !health.provider.configured);
  const empty = !loading && messages.length === 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div
        ref={scrollRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
        className="scroll-thin min-h-0 flex-1 overflow-y-auto"
      >
        {empty ? (
          <div className="flex min-h-full flex-col items-center justify-center px-4 py-10">
            <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.8 }}>
              <AICore state={coreState} size={200} className="sm:w-[240px]!" />
            </motion.div>
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.25 }}
              className="mt-8 text-center"
            >
              <div className="hud-label mb-2">
                {link === "online" ? "All systems nominal" : link === "offline" ? "Uplink lost" : "Establishing uplink"}
              </div>
              <h1 className="text-2xl font-light tracking-tight text-ink sm:text-3xl">
                {greeting()}. <span className="glow-text text-ice">How can I help?</span>
              </h1>
            </motion.div>
            <SetupCard health={health} link={link} error={healthError} />
            {!unavailable && health?.provider.ready !== false && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.45 }}
                className="mt-8 grid w-full max-w-2xl gap-2 sm:grid-cols-2"
              >
                {SUGGESTIONS.map(({ icon: Icon, text }) => (
                  <button
                    key={text}
                    type="button"
                    onClick={() => (text.endsWith(" ") ? onDraft(text) : onSend(text))}
                    className="panel group flex items-center gap-3 rounded-xl px-3.5 py-3 text-left text-sm text-ink-muted transition hover:border-cyan/30 hover:text-ink"
                  >
                    <Icon className="size-4 shrink-0 text-cyan/70 group-hover:text-cyan" />
                    <span>{text.trim()}{text.endsWith(" ") ? "…" : ""}</span>
                  </button>
                ))}
              </motion.div>
            )}
          </div>
        ) : (
          <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-6 sm:px-6">
            {loading && <div className="h-24 animate-pulse rounded-xl bg-white/[0.02]" />}
            {messages.map((m) => (
              <MessageView key={m.id} message={m} />
            ))}
          </div>
        )}
      </div>
      <div className="px-3 pt-2 pb-3 sm:px-6 sm:pb-5">
        <Composer
          onSend={onSend}
          onStop={onStop}
          streaming={streaming}
          disabled={unavailable}
          disabledReason={link === "offline" ? "Backend offline" : "Configure an AI provider to chat"}
          draft={draft}
          onDraftConsumed={onDraftConsumed}
        />
        <p className="mt-2 text-center text-[11px] text-ink-faint">
          NEXUS can make mistakes. File access is read-only and limited to approved folders.
        </p>
      </div>
    </div>
  );
}
