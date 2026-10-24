"use client";

import { isValidElement, memo, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CopyButton } from "./CopyButton";

function textOf(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return textOf(node.props.children);
  return "";
}

function languageOf(node: ReactNode): string | null {
  if (isValidElement<{ className?: string }>(node)) {
    const match = /language-([\w+-]+)/.exec(node.props.className ?? "");
    return match ? match[1] : null;
  }
  return null;
}

/** Renders model output as Markdown. Raw HTML is not rendered (react-markdown escapes it). */
export const Markdown = memo(function Markdown({ text }: { text: string }) {
  return (
    <div className="prose-nexus">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          pre: ({ children }) => {
            const code = textOf(children).replace(/\n$/, "");
            const lang = languageOf(children);
            return (
              <div className="group/code relative overflow-hidden rounded-lg border border-line bg-[#040811]">
                <div className="flex items-center justify-between border-b border-line px-3 py-1">
                  <span className="hud-label">{lang ?? "code"}</span>
                  <CopyButton text={code} className="-mr-1" />
                </div>
                <pre className="scroll-thin overflow-x-auto p-3 font-mono text-[0.82rem] leading-relaxed text-ice">
                  {children}
                </pre>
              </div>
            );
          },
          table: ({ children }) => (
            <div className="scroll-thin overflow-x-auto">
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
});
