"use client";

import { Check, Minus, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import type { Health, ToolInfo } from "@/lib/types";
import type { LinkState } from "@/lib/useHealth";
import { cn } from "@/lib/utils";

const ENV_VARS: Array<[string, string, string]> = [
  ["backend/.env", "NEXUS_PROVIDER", "ollama (free, local) · auto (Anthropic if a key is set) · demo"],
  ["backend/.env", "NEXUS_OLLAMA_MODEL", "Local Ollama model (default qwen3:4b)"],
  ["backend/.env", "NEXUS_OLLAMA_URL", "Ollama server (default http://127.0.0.1:11434)"],
  ["backend/.env", "ANTHROPIC_API_KEY", "Optional Anthropic API key (server-side only)"],
  ["backend/.env", "NEXUS_MODEL", "Anthropic model ID (default claude-opus-5-5)"],
  ["backend/.env", "NEXUS_EFFORT", "Anthropic effort: low · medium · high · xhigh · max"],
  ["backend/.env", "NEXUS_ALLOWED_DIRS", "Comma-separated folders file tools may read"],
  ["frontend/.env.local", "NEXUS_BACKEND_URL", "Where the web server finds the backend"],
];

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="panel brackets rounded-xl p-4">
      <h2 className="hud-label mb-3">{title}</h2>
      {children}
    </section>
  );
}

function KV({ k, v, tone }: { k: string; v: ReactNode; tone?: "ok" | "warn" | "danger" }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-line/60 py-1.5 text-sm last:border-0">
      <span className="text-ink-muted">{k}</span>
      <span
        className={cn(
          "text-right font-mono text-xs",
          tone === "ok" ? "text-ok" : tone === "warn" ? "text-warn" : tone === "danger" ? "text-danger" : "text-ink",
        )}
      >
        {v}
      </span>
    </div>
  );
}

export function SettingsView({
  health,
  link,
  tools,
}: {
  health: Health | null;
  link: LinkState;
  tools: ToolInfo[];
}) {
  const p = health?.provider;
  return (
    <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-4xl space-y-4 px-4 py-6 sm:px-6">
        <div>
          <div className="hud-label mb-1">Settings</div>
          <h1 className="text-xl font-light text-ink">System configuration</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Settings are read from environment files at startup. Secrets never reach the browser.
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <Section title="AI provider">
            <KV
              k="Status"
              v={
                p
                  ? p.demo
                    ? "demo mode"
                    : !p.configured
                      ? "not configured"
                      : p.ready === false
                        ? "not ready"
                        : p.name === "ollama"
                          ? "local · ready"
                          : "configured"
                  : link
              }
              tone={p ? (p.demo || p.ready === false ? "warn" : p.configured ? "ok" : "danger") : undefined}
            />
            <KV k="Provider" v={p?.name ?? "—"} />
            <KV k="Model" v={p?.model ?? "—"} />
            <KV k="Effort" v={p?.effort ?? "—"} />
            <KV k="Refusal fallback" v={p?.refusal_fallback == null ? "—" : p.refusal_fallback ? "on" : "off"} />
            {p && <p className="mt-2 text-xs text-ink-faint">{p.message}</p>}
          </Section>
          <Section title="Backend">
            <KV k="Link" v={link} tone={link === "online" ? "ok" : link === "offline" ? "danger" : undefined} />
            <KV k="Version" v={health?.version ?? "—"} />
            <KV k="Database" v={health?.database ?? "—"} />
            <KV k="Approved directories" v={health?.tools.approved_directories ?? "—"} />
          </Section>
        </div>

        <Section title="Tool registry">
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="text-ink-faint">
                  <th className="py-1.5 pr-3 font-normal">Tool</th>
                  <th className="py-1.5 pr-3 font-normal">Permission</th>
                  <th className="py-1.5 pr-3 font-normal">Implemented</th>
                  <th className="py-1.5 font-normal">Offered to model</th>
                </tr>
              </thead>
              <tbody>
                {tools.map((t) => (
                  <tr key={t.name} className="border-t border-line/60">
                    <td className="py-2 pr-3">
                      <div className="font-mono text-xs text-ice">{t.name}</div>
                      <div className="max-w-sm text-xs text-ink-faint">{t.description}</div>
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs text-ink-muted">
                      {t.permission}
                      {t.requires_approval && <span className="text-warn"> · approval</span>}
                    </td>
                    <td className="py-2 pr-3">
                      {t.implemented ? <Check className="size-4 text-ok" /> : <Minus className="size-4 text-ink-faint" />}
                    </td>
                    <td className="py-2">
                      {t.enabled ? <Check className="size-4 text-ok" /> : <Minus className="size-4 text-ink-faint" />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 flex items-start gap-2 text-xs text-ink-faint">
            <ShieldCheck className="mt-px size-3.5 shrink-0 text-cyan/70" />
            Tools that write files, run commands or act externally stay disabled until an in-app approval
            flow exists. Every call is schema-validated, time-limited, and confined to approved folders.
          </p>
        </Section>

        <Section title="Environment variables">
          <div className="space-y-1.5">
            {ENV_VARS.map(([file, name, desc]) => (
              <div key={name} className="flex flex-wrap items-baseline gap-x-3 text-sm">
                <code className="font-mono text-xs text-ice">{name}</code>
                <span className="text-ink-muted">{desc}</span>
                <span className="font-mono text-[10px] text-ink-faint">{file}</span>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Keyboard">
          <KV k="Send" v="Enter" />
          <KV k="New line" v="Shift + Enter" />
          <KV k="Focus input" v="/" />
          <KV k="Stop generating" v="Esc" />
        </Section>
      </div>
    </div>
  );
}
