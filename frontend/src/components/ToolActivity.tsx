"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  Ban,
  Check,
  ChevronRight,
  FileText,
  FolderTree,
  Loader2,
  Search,
  ShieldAlert,
  Wrench,
} from "lucide-react";
import { useState } from "react";
import type { ToolPart } from "@/lib/types";
import { cn } from "@/lib/utils";

const ICONS: Record<string, typeof Wrench> = {
  list_files: FolderTree,
  search_files: Search,
  read_file: FileText,
};

const LABELS: Record<string, string> = {
  list_files: "List files",
  search_files: "Search files",
  read_file: "Read file",
};

function describeInput(name: string, input: unknown): string {
  if (!input || typeof input !== "object") return "";
  const o = input as Record<string, unknown>;
  if (name === "search_files" && typeof o.query === "string") return `“${o.query}”`;
  if (typeof o.path === "string") return o.path;
  if (name === "list_files") return "approved directories";
  return "";
}

/** One tool call, shown as a visible activity event in the reply. */
export function ToolActivity({ part }: { part: ToolPart }) {
  const [open, setOpen] = useState(false);
  const Icon = ICONS[part.name] ?? Wrench;
  const running = part.status === "running";
  const failed = part.status === "error";

  return (
    <div
      className={cn(
        "brackets my-2 rounded-lg border bg-navy-950/60 text-sm",
        failed ? "border-danger/30" : "border-line",
        running && "scanline",
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-3 py-2 text-left"
        aria-expanded={open}
      >
        <span
          className={cn(
            "grid size-7 shrink-0 place-items-center rounded-md border",
            failed ? "border-danger/30 text-danger" : "border-cyan/25 text-cyan",
          )}
        >
          <Icon className="size-3.5" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="font-medium text-ink">{LABELS[part.name] ?? part.name}</span>
            <span className="hud-label hidden sm:inline">read-only</span>
          </span>
          <span className="block truncate font-mono text-xs text-ink-muted">
            {part.summary && !running ? part.summary : describeInput(part.name, part.input)}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-2 text-xs text-ink-faint">
          {typeof part.duration_ms === "number" && !running && (
            <span className="font-mono">{part.duration_ms} ms</span>
          )}
          {running && <Loader2 className="size-4 animate-spin text-cyan" />}
          {part.status === "ok" && <Check className="size-4 text-ok" />}
          {failed && <ShieldAlert className="size-4 text-danger" />}
          {part.status === "cancelled" && <Ban className="size-4 text-ink-faint" />}
          <ChevronRight className={cn("size-4 transition", open && "rotate-90")} />
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="space-y-2 border-t border-line px-3 py-2 font-mono text-xs">
              <div>
                <span className="hud-label">input</span>
                <pre className="scroll-thin mt-1 overflow-x-auto whitespace-pre-wrap text-ice-dim">
                  {JSON.stringify(part.input, null, 2)}
                </pre>
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-ink-muted">
                <span>
                  <span className="hud-label">status</span> {part.status}
                </span>
                {part.error_code && (
                  <span>
                    <span className="hud-label">code</span> {part.error_code}
                  </span>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
