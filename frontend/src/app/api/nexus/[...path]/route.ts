import type { NextRequest } from "next/server";

/**
 * Same-origin proxy from the browser to the Python backend.
 *
 * The browser only ever talks to this Next.js server; the backend URL comes from
 * the server-side NEXUS_BACKEND_URL variable and no provider credentials ever
 * pass through here. Responses (including SSE streams) are piped through as-is,
 * and aborting the browser request aborts the upstream one.
 */

const BACKEND_URL = process.env.NEXUS_BACKEND_URL ?? "http://127.0.0.1:8000";
const ALLOWED_PREFIXES = new Set(["health", "tools", "files", "conversations", "chat"]);

type Ctx = RouteContext<"/api/nexus/[...path]">;

function jsonError(status: number, code: string, message: string) {
  return Response.json({ error: { code, message } }, { status });
}

async function proxy(request: NextRequest, ctx: Ctx): Promise<Response> {
  const { path } = await ctx.params;
  if (!path.length || !ALLOWED_PREFIXES.has(path[0])) {
    return jsonError(404, "not_found", "Unknown API route.");
  }
  const target = new URL(`/api/${path.map(encodeURIComponent).join("/")}`, BACKEND_URL);
  target.search = request.nextUrl.search;

  const hasBody = !["GET", "HEAD"].includes(request.method);
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers: {
        "content-type": request.headers.get("content-type") ?? "application/json",
        accept: request.headers.get("accept") ?? "application/json",
      },
      body: hasBody ? await request.arrayBuffer() : undefined,
      signal: request.signal,
      cache: "no-store",
    });
  } catch (err) {
    if (request.signal.aborted) return new Response(null, { status: 499 });
    console.error("[nexus proxy]", err);
    return jsonError(
      502,
      "backend_unreachable",
      `Cannot reach the NEXUS backend at ${BACKEND_URL}. Is it running?`,
    );
  }

  const headers = new Headers();
  for (const name of ["content-type", "cache-control"]) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (headers.get("content-type")?.startsWith("text/event-stream")) {
    headers.set("cache-control", "no-cache, no-transform");
    headers.set("x-accel-buffering", "no");
  }
  const body = upstream.status === 204 ? null : upstream.body;
  return new Response(body, { status: upstream.status, headers });
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
