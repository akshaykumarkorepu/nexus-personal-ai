"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { cn, copyText } from "@/lib/utils";

export function CopyButton({
  text,
  label = "Copy",
  className,
}: {
  text: string;
  label?: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        if (await copyText(text)) {
          setCopied(true);
          setTimeout(() => setCopied(false), 1400);
        }
      }}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-ink-faint transition hover:bg-white/5 hover:text-ice",
        className,
      )}
      aria-label={copied ? "Copied" : label}
      title={label}
    >
      {copied ? <Check className="size-3.5 text-ok" /> : <Copy className="size-3.5" />}
      <span>{copied ? "Copied" : label}</span>
    </button>
  );
}
