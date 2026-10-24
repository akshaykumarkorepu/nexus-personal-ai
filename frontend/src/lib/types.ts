export type MessageStatus = "streaming" | "complete" | "stopped" | "error";

export type TextPart = { type: "text"; text: string };
export type ToolPart = {
  type: "tool";
  id: string;
  name: string;
  input: unknown;
  status: "running" | "ok" | "error" | "cancelled";
  summary?: string;
  duration_ms?: number;
  error_code?: string | null;
};
export type NoticePart = { type: "notice"; level: "info" | "warning"; text: string };
export type MessagePart = TextPart | ToolPart | NoticePart;

export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  parts: MessagePart[];
  status: MessageStatus;
  error: string | null;
  provider: string | null;
  created_at: string;
  updated_at: string;
  /** Client-only: the model is reasoning before it writes. */
  thinking?: boolean;
}

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ChatMessage[];
}

export interface Health {
  status: "ok";
  version: string;
  database: "ok" | "error";
  provider: {
    name: "anthropic" | "ollama" | "demo" | "unconfigured";
    configured: boolean;
    /** Result of a cheap readiness probe (local providers only); null when not probed. */
    ready: boolean | null;
    demo: boolean;
    model: string;
    effort: string | null;
    refusal_fallback: boolean | null;
    message: string;
  };
  tools: { available: string[]; approved_directories: number };
}

export interface ToolInfo {
  name: string;
  description: string;
  category: string;
  permission: "read_only" | "write" | "execute" | "external";
  requires_approval: boolean;
  implemented: boolean;
  enabled: boolean;
}

export interface FileRoot {
  path: string;
  display: string;
  name: string;
}

export interface FileEntry {
  name: string;
  path: string;
  type: "file" | "dir" | "symlink";
  size: number | null;
  modified: string | null;
  readable: boolean;
}

export type StreamEvent =
  | {
      type: "meta";
      conversation_id: string;
      title: string;
      user_message: ChatMessage;
      assistant_message_id: string;
      provider: string;
      model: string;
      demo: boolean;
    }
  | { type: "status"; state: "thinking" }
  | { type: "text"; delta: string }
  | { type: "tool_start"; id: string; name: string; input: unknown }
  | {
      type: "tool_end";
      id: string;
      name: string;
      ok: boolean;
      summary: string;
      duration_ms: number;
      error_code: string | null;
    }
  | { type: "notice"; level: "info" | "warning"; text: string }
  | { type: "error"; code: string; message: string }
  | {
      type: "done";
      status: MessageStatus;
      stop_reason: string | null;
      usage: Record<string, number>;
    };
