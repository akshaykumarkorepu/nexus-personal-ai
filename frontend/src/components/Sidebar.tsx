"use client";

import {
  FolderGit2,
  FolderOpen,
  ListChecks,
  MessageSquare,
  Plus,
  Settings2,
  Trash2,
  X,
} from "lucide-react";
import type { ConversationSummary } from "@/lib/types";
import { cn, relativeTime } from "@/lib/utils";
import { AICore, type CoreState } from "./AICore";

export type View = "chat" | "files" | "projects" | "tasks" | "settings";

const NAV: Array<{ id: View; label: string; icon: typeof MessageSquare; soon?: boolean }> = [
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "files", label: "Files", icon: FolderOpen },
  { id: "projects", label: "Projects", icon: FolderGit2, soon: true },
  { id: "tasks", label: "Tasks", icon: ListChecks, soon: true },
  { id: "settings", label: "Settings", icon: Settings2 },
];

export function Sidebar({
  view,
  onView,
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
  coreState,
  version,
  listError,
  open,
  onClose,
}: {
  view: View;
  onView: (v: View) => void;
  conversations: ConversationSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  coreState: CoreState;
  version?: string;
  listError: string | null;
  open: boolean;
  onClose: () => void;
}) {
  return (
    <>
      <div
        className={cn(
          "fixed inset-0 z-30 bg-black/60 backdrop-blur-sm transition lg:hidden",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={onClose}
        aria-hidden
      />
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-[272px] flex-col border-r border-line bg-abyss/95 backdrop-blur-xl transition-transform duration-300 lg:static lg:translate-x-0 lg:bg-abyss/60",
          open ? "translate-x-0" : "-translate-x-full",
        )}
        aria-label="Primary"
      >
        <div className="flex items-center gap-3 px-5 pt-5 pb-4">
          <AICore state={coreState} size={34} />
          <div className="min-w-0 flex-1">
            <div className="glow-text font-mono text-[15px] font-semibold tracking-[0.32em] text-ice">
              NEXUS
            </div>
            <div className="hud-label !text-[9px]">Personal intelligence · v{version ?? "—"}</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-ink-faint hover:text-ice lg:hidden"
            aria-label="Close menu"
          >
            <X className="size-4" />
          </button>
        </div>

        <nav className="space-y-0.5 px-3">
          {NAV.map(({ id, label, icon: Icon, soon }) => {
            const active = view === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => onView(id)}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "group relative flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition",
                  active
                    ? "bg-cyan/[0.08] text-ice"
                    : "text-ink-muted hover:bg-white/[0.03] hover:text-ink",
                )}
              >
                {active && (
                  <span className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-cyan shadow-[0_0_10px_rgba(34,211,238,0.9)]" />
                )}
                <Icon className={cn("size-4", active ? "text-cyan" : "text-ink-faint group-hover:text-ice-dim")} />
                <span className="flex-1 text-left">{label}</span>
                {soon && <span className="hud-label !text-[8.5px] !tracking-[0.12em]">soon</span>}
              </button>
            );
          })}
        </nav>

        <div className="mt-5 flex items-center justify-between px-5 pb-2">
          <span className="hud-label">Conversations</span>
          <button
            type="button"
            onClick={onNew}
            className="flex items-center gap-1 rounded-md border border-line px-2 py-1 text-xs text-ink-muted transition hover:border-cyan/40 hover:text-cyan"
            title="New conversation"
          >
            <Plus className="size-3.5" /> New
          </button>
        </div>
        <div className="scroll-thin min-h-0 flex-1 space-y-0.5 overflow-y-auto px-3 pb-4">
          {listError && <p className="px-2 py-1 text-xs text-warn">{listError}</p>}
          {!listError && conversations.length === 0 && (
            <p className="px-2 py-2 text-xs text-ink-faint">No conversations yet.</p>
          )}
          {conversations.map((c) => {
            const active = c.id === activeId;
            return (
              <div
                key={c.id}
                className={cn(
                  "group flex items-center rounded-lg transition",
                  active ? "bg-white/[0.05]" : "hover:bg-white/[0.03]",
                )}
              >
                <button
                  type="button"
                  onClick={() => onSelect(c.id)}
                  className="min-w-0 flex-1 px-3 py-2 text-left"
                  aria-current={active ? "true" : undefined}
                >
                  <div className={cn("truncate text-[13px]", active ? "text-ink" : "text-ink-muted")}>
                    {c.title}
                  </div>
                  <div className="font-mono text-[10px] text-ink-faint">
                    {relativeTime(c.updated_at)} · {c.message_count} msg
                  </div>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (window.confirm(`Delete “${c.title}”? This cannot be undone.`)) onDelete(c.id);
                  }}
                  className="mr-1.5 rounded p-1.5 text-ink-faint opacity-0 transition group-hover:opacity-100 hover:text-danger focus:opacity-100"
                  aria-label={`Delete ${c.title}`}
                  title="Delete conversation"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            );
          })}
        </div>
      </aside>
    </>
  );
}
