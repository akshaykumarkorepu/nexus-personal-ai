import type {
  ConversationDetail,
  ConversationSummary,
  FileEntry,
  FileRoot,
  Health,
  StreamEvent,
  ToolInfo,
} from "./types";

/** Same-origin proxy to the Python backend (see app/api/nexus/[...path]/route.ts). */
const BASE = "/api/nexus";

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = (await res.json()) as { error?: { code?: string; message?: string } };
    return new ApiError(
      body.error?.code ?? "http_error",
      body.error?.message ?? `Request failed (${res.status})`,
      res.status,
    );
  } catch {
    return new ApiError("http_error", `Request failed (${res.status})`, res.status);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new ApiError("network_error", "Cannot reach the NEXUS web server.", 0);
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  health: () => request<Health>("/health"),
  tools: () => request<{ approval_flow_available: boolean; tools: ToolInfo[] }>("/tools"),
  conversations: () => request<ConversationSummary[]>("/conversations"),
  conversation: (id: string) => request<ConversationDetail>(`/conversations/${id}`),
  rename: (id: string, title: string) =>
    request<ConversationSummary>(`/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  remove: (id: string) => request<void>(`/conversations/${id}`, { method: "DELETE" }),
  fileRoots: () => request<{ roots: FileRoot[] }>("/files/roots"),
  listDir: (path: string) =>
    request<{ path: string; display: string; entries: FileEntry[] }>(
      `/files/list?path=${encodeURIComponent(path)}`,
    ),
};

/**
 * POST a chat message and yield server-sent events as they arrive.
 * Abort the signal to stop generation; the backend records the reply as stopped.
 */
export async function* streamChat(
  message: string,
  conversationId: string | null,
  signal: AbortSignal,
): AsyncGenerator<StreamEvent> {
  let res: Response;
  try {
    res = await fetch(`${BASE}/chat`, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "text/event-stream" },
      body: JSON.stringify({ message, conversation_id: conversationId }),
      signal,
    });
  } catch (err) {
    if (signal.aborted) return;
    throw err instanceof Error && err.name === "AbortError"
      ? err
      : new ApiError("network_error", "Cannot reach the NEXUS web server.", 0);
  }
  if (!res.ok || !res.body) throw await parseError(res);

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;
      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const data = frame
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");
        if (data) yield JSON.parse(data) as StreamEvent;
      }
    }
  } catch (err) {
    if (signal.aborted) return;
    throw err;
  } finally {
    reader.releaseLock();
  }
}
