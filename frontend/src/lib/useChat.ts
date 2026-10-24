"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, streamChat } from "./api";
import type { ChatMessage, ConversationSummary, MessagePart, ToolPart } from "./types";

const ACTIVE_KEY = "nexus:active-conversation";

function readActive(): string | null {
  try {
    return localStorage.getItem(ACTIVE_KEY);
  } catch {
    return null;
  }
}

function writeActive(id: string | null) {
  try {
    if (id) localStorage.setItem(ACTIVE_KEY, id);
    else localStorage.removeItem(ACTIVE_KEY);
  } catch {
    // Storage unavailable (private mode); the active chat just won't be remembered.
  }
}

function placeholder(role: "user" | "assistant", parts: MessagePart[]): ChatMessage {
  const now = new Date().toISOString();
  return {
    id: `local-${role}-${crypto.randomUUID()}`,
    conversation_id: "",
    role,
    parts,
    status: role === "user" ? "complete" : "streaming",
    error: null,
    provider: null,
    created_at: now,
    updated_at: now,
  };
}

export function useChat() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [lastUsage, setLastUsage] = useState<Record<string, number> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const replyIdRef = useRef<string | null>(null);

  const refreshList = useCallback(async () => {
    try {
      setConversations(await api.conversations());
      setListError(null);
    } catch (err) {
      setListError(err instanceof ApiError ? err.message : "Could not load conversations.");
    }
  }, []);

  const load = useCallback(async (id: string) => {
    setLoading(true);
    try {
      const detail = await api.conversation(id);
      setActiveId(id);
      setMessages(detail.messages);
      writeActive(id);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        writeActive(null);
        setActiveId(null);
        setMessages([]);
      } else {
        setListError(err instanceof ApiError ? err.message : "Could not load the conversation.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  // Restore the conversation list and the last active conversation after a refresh.
  useEffect(() => {
    let cancelled = false;
    const restore = async () => {
      await refreshList();
      const id = readActive();
      if (id) await load(id);
      else if (!cancelled) setLoading(false);
    };
    void restore();
    return () => {
      cancelled = true;
    };
  }, [load, refreshList]);

  const patchReply = useCallback((fn: (m: ChatMessage) => ChatMessage) => {
    const id = replyIdRef.current;
    setMessages((prev) => prev.map((m) => (m.id === id ? fn(m) : m)));
  }, []);

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const select = useCallback(
    async (id: string) => {
      if (id === activeId) return;
      abortRef.current?.abort();
      await load(id);
    },
    [activeId, load],
  );

  const newChat = useCallback(() => {
    abortRef.current?.abort();
    setActiveId(null);
    setMessages([]);
    setLastUsage(null);
    writeActive(null);
  }, []);

  const remove = useCallback(
    async (id: string) => {
      await api.remove(id);
      if (id === activeId) newChat();
      await refreshList();
    },
    [activeId, newChat, refreshList],
  );

  const rename = useCallback(
    async (id: string, title: string) => {
      await api.rename(id, title);
      await refreshList();
    },
    [refreshList],
  );

  const send = useCallback(
    async (text: string) => {
      if (streaming) return;
      const user = placeholder("user", [{ type: "text", text }]);
      const reply = placeholder("assistant", []);
      replyIdRef.current = reply.id;
      setMessages((prev) => [...prev, user, reply]);
      setStreaming(true);
      const controller = new AbortController();
      abortRef.current = controller;
      let finished = false;

      try {
        for await (const ev of streamChat(text, activeId, controller.signal)) {
          switch (ev.type) {
            case "meta": {
              setActiveId(ev.conversation_id);
              writeActive(ev.conversation_id);
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === user.id
                    ? ev.user_message
                    : m.id === reply.id
                      ? { ...m, id: ev.assistant_message_id, conversation_id: ev.conversation_id, provider: ev.provider }
                      : m,
                ),
              );
              replyIdRef.current = ev.assistant_message_id;
              void refreshList();
              break;
            }
            case "status":
              patchReply((m) => ({ ...m, thinking: true }));
              break;
            case "text":
              patchReply((m) => {
                const parts = [...m.parts];
                const last = parts[parts.length - 1];
                if (last?.type === "text") parts[parts.length - 1] = { ...last, text: last.text + ev.delta };
                else parts.push({ type: "text", text: ev.delta });
                return { ...m, parts, thinking: false };
              });
              break;
            case "tool_start":
              patchReply((m) => ({
                ...m,
                thinking: false,
                parts: [
                  ...m.parts,
                  { type: "tool", id: ev.id, name: ev.name, input: ev.input, status: "running" },
                ],
              }));
              break;
            case "tool_end":
              patchReply((m) => ({
                ...m,
                parts: m.parts.map((p) =>
                  p.type === "tool" && p.id === ev.id
                    ? ({
                        ...p,
                        status: ev.ok ? "ok" : "error",
                        summary: ev.summary,
                        duration_ms: ev.duration_ms,
                        error_code: ev.error_code,
                      } satisfies ToolPart)
                    : p,
                ),
              }));
              break;
            case "notice":
              patchReply((m) => ({
                ...m,
                parts: [...m.parts, { type: "notice", level: ev.level, text: ev.text }],
              }));
              break;
            case "error":
              patchReply((m) => ({ ...m, status: "error", error: ev.message, thinking: false }));
              break;
            case "done":
              finished = true;
              setLastUsage(ev.usage);
              patchReply((m) => ({
                ...m,
                status: m.status === "error" ? "error" : ev.status,
                thinking: false,
              }));
              break;
          }
        }
        if (!finished) {
          patchReply((m) =>
            m.status === "streaming"
              ? {
                  ...m,
                  status: "stopped",
                  thinking: false,
                  parts: m.parts.map((p) => (p.type === "tool" && p.status === "running" ? { ...p, status: "cancelled" } : p)),
                }
              : m,
          );
        }
      } catch (err) {
        const message =
          err instanceof ApiError ? err.message : "The connection to NEXUS was interrupted.";
        patchReply((m) => ({ ...m, status: "error", error: message, thinking: false }));
      } finally {
        abortRef.current = null;
        setStreaming(false);
        void refreshList();
      }
    },
    [activeId, patchReply, refreshList, streaming],
  );

  return {
    conversations,
    activeId,
    messages,
    streaming,
    loading,
    listError,
    lastUsage,
    send,
    stop,
    select,
    newChat,
    remove,
    rename,
    refreshList,
  };
}
