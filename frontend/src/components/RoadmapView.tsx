"use client";

import { CircleDashed, Lock } from "lucide-react";
import type { ToolInfo } from "@/lib/types";

const PERMISSION_LABEL: Record<ToolInfo["permission"], string> = {
  read_only: "Read-only",
  write: "Writes files · approval required",
  execute: "Runs commands · approval required",
  external: "External actions · approval required",
};

export interface RoadmapItem {
  title: string;
  description: string;
  tool?: string;
}

/** Honest placeholder for areas that are designed but not built yet. */
export function RoadmapView({
  label,
  title,
  intro,
  items,
  tools,
}: {
  label: string;
  title: string;
  intro: string;
  items: RoadmapItem[];
  tools: ToolInfo[];
}) {
  return (
    <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-4xl px-4 py-6 sm:px-6">
        <div className="hud-label mb-1">{label}</div>
        <h1 className="text-xl font-light text-ink">{title}</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-muted">{intro}</p>
        <div className="mt-3 inline-flex items-center gap-2 rounded-md border border-warn/30 bg-warn/5 px-2.5 py-1 font-mono text-[11px] tracking-wider text-warn">
          <CircleDashed className="size-3.5" /> NOT YET IMPLEMENTED
        </div>
        <div className="mt-6 grid gap-3 sm:grid-cols-2">
          {items.map((item) => {
            const tool = item.tool ? tools.find((t) => t.name === item.tool) : undefined;
            return (
              <div key={item.title} className="panel brackets rounded-xl p-4">
                <div className="flex items-start justify-between gap-3">
                  <h2 className="text-sm font-medium text-ink">{item.title}</h2>
                  <span className="hud-label shrink-0 !text-[9px]">planned</span>
                </div>
                <p className="mt-1.5 text-sm text-ink-muted">{item.description}</p>
                {tool && (
                  <div className="mt-3 flex items-center gap-2 font-mono text-[11px] text-ink-faint">
                    <Lock className="size-3" />
                    <span className="text-ice-dim">{tool.name}</span>·<span>{PERMISSION_LABEL[tool.permission]}</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
