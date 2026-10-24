"use client";

import { Activity, Cpu, Database, FolderLock, Gauge, Wrench } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import type { LinkState } from "@/lib/useHealth";
import type { Health } from "@/lib/types";
import { cn } from "@/lib/utils";
import { AICore, type CoreState } from "./AICore";

function Panel({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <section className="brackets panel rounded-xl p-3.5">
      <header className="mb-2 flex items-center gap-2">
        <span className="text-cyan/80">{icon}</span>
        <span className="hud-label">{title}</span>
      </header>
      {children}
    </section>
  );
}

function Row({ label, value, tone }: { label: string; value: ReactNode; tone?: "ok" | "warn" | "danger" }) {
  return (
    <div className="flex items-center justify-between gap-3 py-0.5 text-xs">
      <span className="text-ink-faint">{label}</span>
      <span
        className={cn(
          "truncate font-mono",
          tone === "ok" && "text-ok",
          tone === "warn" && "text-warn",
          tone === "danger" && "text-danger",
          !tone && "text-ink",
        )}
      >
        {value}
      </span>
    </div>
  );
}

function Clock() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="text-right">
      <div className="font-mono text-2xl font-light tracking-wider text-ice tabular-nums">
        {now ? now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "--:--:--"}
      </div>
      <div className="hud-label">
        {now ? now.toLocaleDateString([], { weekday: "long", month: "short", day: "numeric" }) : " "}
      </div>
    </div>
  );
}

const CORE_LABEL: Record<CoreState, string> = {
  idle: "Standing by",
  thinking: "Reasoning",
  speaking: "Responding",
  error: "Fault",
  offline: "Offline",
};

export function StatusRail({
  health,
  link,
  latency,
  coreState,
  lastUsage,
}: {
  health: Health | null;
  link: LinkState;
  latency: number | null;
  coreState: CoreState;
  lastUsage: Record<string, number> | null;
}) {
  const p = health?.provider;
  const providerTone = !p
    ? undefined
    : p.ready === false
      ? "warn"
      : p.name === "anthropic" || p.name === "ollama"
        ? "ok"
        : p.demo
          ? "warn"
          : "danger";
  return (
    <aside className="scroll-thin hidden w-[264px] shrink-0 space-y-3 overflow-y-auto border-l border-line p-4 xl:block">
      <Clock />

      <Panel title="Core" icon={<Activity className="size-3.5" />}>
        <div className="flex items-center gap-3">
          <AICore state={coreState} size={44} />
          <div>
            <div className="text-sm text-ink">{CORE_LABEL[coreState]}</div>
            <div className="font-mono text-[10px] text-ink-faint">state: {coreState}</div>
          </div>
        </div>
      </Panel>

      <Panel title="Uplink" icon={<Database className="size-3.5" />}>
        <Row
          label="Backend"
          value={link === "online" ? "online" : link === "offline" ? "unreachable" : "checking"}
          tone={link === "online" ? "ok" : link === "offline" ? "danger" : undefined}
        />
        <Row label="Latency" value={latency !== null ? `${latency} ms` : "—"} />
        <Row label="Database" value={health?.database ?? "—"} tone={health?.database === "ok" ? "ok" : undefined} />
      </Panel>

      <Panel title="Model" icon={<Cpu className="size-3.5" />}>
        <Row
          label="Provider"
          value={p ? (p.demo ? "demo" : p.name) : "—"}
          tone={providerTone}
        />
        <Row label="Model" value={p?.configured && !p.demo ? p.model : "—"} />
        <Row label="Effort" value={p?.effort ?? "—"} />
      </Panel>

      <Panel title="Tools" icon={<Wrench className="size-3.5" />}>
        <Row label="Active (read-only)" value={health?.tools.available.length ?? "—"} />
        <Row label="Approval-gated" value="off" />
        <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-ink-faint">
          <FolderLock className="size-3" />
          {health ? `${health.tools.approved_directories} approved director${health.tools.approved_directories === 1 ? "y" : "ies"}` : "—"}
        </div>
      </Panel>

      <Panel title="Last reply" icon={<Gauge className="size-3.5" />}>
        <Row label="Input tokens" value={lastUsage?.input_tokens?.toLocaleString() ?? "—"} />
        <Row label="Output tokens" value={lastUsage?.output_tokens?.toLocaleString() ?? "—"} />
        <Row label="Cache reads" value={lastUsage?.cache_read_input_tokens?.toLocaleString() ?? "—"} />
      </Panel>
    </aside>
  );
}
