"use client";

import {
  ChevronRight,
  File,
  FileText,
  Folder,
  FolderLock,
  HardDrive,
  Link2,
  Loader2,
  MessageSquarePlus,
  NotebookPen,
  RefreshCw,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { FileEntry, FileRoot } from "@/lib/types";
import { cn, formatBytes, relativeTime } from "@/lib/utils";

export function FilesView({ onAsk }: { onAsk: (prompt: string) => void }) {
  const [roots, setRoots] = useState<FileRoot[] | null>(null);
  const [root, setRoot] = useState<FileRoot | null>(null);
  const [path, setPath] = useState<string | null>(null);
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadRoots = useCallback(async () => {
    try {
      const r = await api.fileRoots();
      setRoots(r.roots);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load approved folders.");
    }
  }, []);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => void loadRoots(), [loadRoots]);

  const open = useCallback(async (target: string) => {
    setBusy(true);
    try {
      const res = await api.listDir(target);
      setPath(res.path);
      setEntries(res.entries);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not open folder.");
    } finally {
      setBusy(false);
    }
  }, []);

  const crumbs = (() => {
    if (!root || !path) return [];
    const rel = path.slice(root.path.length).split("/").filter(Boolean);
    return [
      { label: root.name, path: root.path },
      ...rel.map((seg, i) => ({ label: seg, path: `${root.path}/${rel.slice(0, i + 1).join("/")}` })),
    ];
  })();

  return (
    <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-4xl px-4 py-6 sm:px-6">
        <header className="mb-6 flex items-end justify-between gap-4">
          <div>
            <div className="hud-label mb-1">Files</div>
            <h1 className="text-xl font-light text-ink">Approved directories</h1>
            <p className="mt-1 max-w-xl text-sm text-ink-muted">
              NEXUS can list, search and read text and PDF files here, read-only. Keys, credentials and
              <code className="mx-1 font-mono text-xs text-ice-dim">.env</code>files are always hidden.
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              void loadRoots();
              if (path) void open(path);
            }}
            className="rounded-lg border border-line p-2 text-ink-muted transition hover:text-ice"
            aria-label="Refresh"
          >
            <RefreshCw className={cn("size-4", busy && "animate-spin")} />
          </button>
        </header>

        {error && (
          <div role="alert" className="mb-4 rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
            {error}
          </div>
        )}

        {roots === null && !error && <Loader2 className="size-5 animate-spin text-cyan" />}

        {roots?.length === 0 && (
          <div className="panel brackets rounded-xl p-5 text-sm">
            <div className="mb-2 flex items-center gap-2 text-warn">
              <FolderLock className="size-4" /> No folders approved yet
            </div>
            <p className="text-ink-muted">
              Add absolute paths to <code className="font-mono text-ice-dim">NEXUS_ALLOWED_DIRS</code> in{" "}
              <code className="font-mono text-ice-dim">backend/.env</code> (comma-separated), then restart the backend.
            </p>
            <pre className="mt-3 overflow-x-auto rounded-lg bg-black/40 p-3 font-mono text-xs text-ice">
              NEXUS_ALLOWED_DIRS=/Users/you/Documents/Notes,/Users/you/Projects
            </pre>
          </div>
        )}

        {roots && roots.length > 0 && (
          <div className="mb-5 grid gap-2 sm:grid-cols-2">
            {roots.map((r) => (
              <button
                key={r.path}
                type="button"
                onClick={() => {
                  setRoot(r);
                  void open(r.path);
                }}
                className={cn(
                  "panel brackets flex items-center gap-3 rounded-xl px-4 py-3 text-left transition hover:border-cyan/30",
                  root?.path === r.path && "border-cyan/40",
                )}
              >
                <HardDrive className="size-4 text-cyan" />
                <div className="min-w-0">
                  <div className="truncate text-sm text-ink">{r.name}</div>
                  <div className="truncate font-mono text-[11px] text-ink-faint">{r.display}</div>
                </div>
              </button>
            ))}
          </div>
        )}

        {path && (
          <div className="panel overflow-hidden rounded-xl">
            <div className="flex flex-wrap items-center gap-1 border-b border-line px-3 py-2 text-xs">
              {crumbs.map((c, i) => (
                <span key={c.path} className="flex items-center gap-1">
                  {i > 0 && <ChevronRight className="size-3 text-ink-faint" />}
                  <button
                    type="button"
                    onClick={() => void open(c.path)}
                    className={cn(
                      "rounded px-1 py-0.5 font-mono hover:text-ice",
                      i === crumbs.length - 1 ? "text-ice" : "text-ink-muted",
                    )}
                  >
                    {c.label}
                  </button>
                </span>
              ))}
            </div>
            {entries.length === 0 && <p className="px-4 py-6 text-sm text-ink-faint">Empty folder.</p>}
            <ul className="divide-y divide-line">
              {entries.map((e) => {
                const Icon =
                  e.type === "dir" ? Folder : e.type === "symlink" ? Link2 : e.readable ? FileText : File;
                const isPdf = e.name.toLowerCase().endsWith(".pdf");
                return (
                  <li key={e.path} className="group flex items-center gap-3 px-3 py-2 text-sm hover:bg-white/[0.02]">
                    <Icon className={cn("size-4 shrink-0", e.type === "dir" ? "text-cyan/80" : "text-ink-faint")} />
                    {e.type === "dir" ? (
                      <button type="button" onClick={() => void open(e.path)} className="min-w-0 flex-1 truncate text-left text-ink hover:text-ice">
                        {e.name}
                      </button>
                    ) : (
                      <span className={cn("min-w-0 flex-1 truncate", e.readable ? "text-ink" : "text-ink-faint")}>
                        {e.name}
                      </span>
                    )}
                    <span className="hidden font-mono text-[11px] text-ink-faint sm:inline">{formatBytes(e.size)}</span>
                    <span className="hidden w-16 text-right font-mono text-[11px] text-ink-faint md:inline">
                      {e.modified ? relativeTime(e.modified) : ""}
                    </span>
                    {e.type === "file" && e.readable && (
                      <span className="flex gap-1 opacity-100 transition sm:opacity-0 sm:group-hover:opacity-100">
                        {isPdf && (
                          <button
                            type="button"
                            onClick={() => onAsk(`Create concise revision notes from the PDF at ${e.path}`)}
                            className="rounded-md border border-line p-1.5 text-ink-muted hover:border-cyan/40 hover:text-cyan"
                            title="Draft a revision-notes request"
                          >
                            <NotebookPen className="size-3.5" />
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => onAsk(`Summarize the file ${e.path}`)}
                          className="rounded-md border border-line p-1.5 text-ink-muted hover:border-cyan/40 hover:text-cyan"
                          title="Ask NEXUS about this file"
                        >
                          <MessageSquarePlus className="size-3.5" />
                        </button>
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
