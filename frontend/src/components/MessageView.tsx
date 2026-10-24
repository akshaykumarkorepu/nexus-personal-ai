"use client";

import { motion } from "framer-motion";
import { AlertTriangle, CircleStop, Info } from "lucide-react";
import type { ChatMessage } from "@/lib/types";
import { cn } from "@/lib/utils";
import { AICore } from "./AICore";
import { CopyButton } from "./CopyButton";
import { Markdown } from "./Markdown";
import { ToolActivity } from "./ToolActivity";

function plainText(message: ChatMessage): string {
  return message.parts
    .filter((p) => p.type === "text")
    .map((p) => p.text)
    .join("\n\n")
    .trim();
}

export function MessageView({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    const text = plainText(message);
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="group flex justify-end"
      >
        <div className="max-w-[85%] sm:max-w-[75%]">
          <div className="rounded-2xl rounded-br-md border border-cyan/20 bg-gradient-to-br from-cyan/[0.13] to-sky-500/[0.06] px-4 py-2.5 text-[0.95rem] leading-relaxed whitespace-pre-wrap text-ink shadow-[0_0_30px_-12px_rgba(34,211,238,0.4)]">
            {text}
          </div>
          <div className="mt-1 flex justify-end opacity-0 transition group-hover:opacity-100">
            <CopyButton text={text} />
          </div>
        </div>
      </motion.div>
    );
  }

  const streaming = message.status === "streaming";
  const text = plainText(message);
  const lastPart = message.parts[message.parts.length - 1];
  const showCaret = streaming && lastPart?.type === "text";
  const waiting = streaming && (!lastPart || lastPart.type !== "text");
  const demo = message.provider === "demo";

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="group flex gap-3">
      <div className="mt-0.5 hidden sm:block">
        <AICore state={streaming ? "speaking" : message.status === "error" ? "error" : "idle"} size={28} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2">
          <span className="font-mono text-[11px] tracking-[0.2em] text-cyan">NEXUS</span>
          {demo && (
            <span className="rounded border border-warn/40 bg-warn/10 px-1.5 py-px font-mono text-[10px] tracking-wider text-warn">
              DEMO · NO MODEL
            </span>
          )}
        </div>

        {message.parts.map((part, i) => {
          if (part.type === "tool") return <ToolActivity key={part.id} part={part} />;
          if (part.type === "notice")
            return (
              <div
                key={i}
                className={cn(
                  "my-2 flex items-start gap-2 rounded-lg border px-3 py-2 text-sm",
                  part.level === "warning"
                    ? "border-warn/30 bg-warn/5 text-warn"
                    : "border-line bg-navy-900/40 text-ink-muted",
                )}
              >
                <Info className="mt-0.5 size-4 shrink-0" />
                <span>{part.text}</span>
              </div>
            );
          const isLast = i === message.parts.length - 1;
          return (
            <div key={i} className={cn(isLast && showCaret && "streaming-caret")}>
              <Markdown text={part.text} />
            </div>
          );
        })}

        {waiting && (
          <div className="flex items-center gap-2 py-2 text-sm text-ink-muted">
            <span className="relative flex size-2">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-cyan/60" />
              <span className="relative inline-flex size-2 rounded-full bg-cyan" />
            </span>
            <span className="font-mono text-xs tracking-wider">
              {message.thinking ? "REASONING" : message.parts.length ? "WORKING" : "CONNECTING"}
            </span>
          </div>
        )}

        {message.status === "stopped" && (
          <div className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-line px-2 py-1 text-xs text-ink-muted">
            <CircleStop className="size-3.5" /> Stopped{message.error ? ` · ${message.error}` : ""}
          </div>
        )}
        {message.status === "error" && (
          <div
            role="alert"
            className="mt-2 flex items-start gap-2 rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger"
          >
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span>{message.error ?? "Something went wrong."}</span>
          </div>
        )}

        {!streaming && text && (
          <div className="mt-1 -ml-2 opacity-60 transition group-hover:opacity-100">
            <CopyButton text={text} label="Copy response" />
          </div>
        )}
      </div>
    </motion.div>
  );
}
