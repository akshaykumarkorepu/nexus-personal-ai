"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api";
import type { Health } from "./types";

export type LinkState = "checking" | "online" | "offline";

export function useHealth(intervalMs = 15_000) {
  const [health, setHealth] = useState<Health | null>(null);
  const [link, setLink] = useState<LinkState>("checking");
  const [latency, setLatency] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const check = useCallback(async () => {
    const started = performance.now();
    try {
      const h = await api.health();
      setHealth(h);
      setLink("online");
      setLatency(Math.round(performance.now() - started));
      setError(null);
    } catch (err) {
      setLink("offline");
      setLatency(null);
      setError(err instanceof ApiError ? err.message : "Backend unreachable.");
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void check();
    const id = setInterval(check, intervalMs);
    return () => clearInterval(id);
  }, [check, intervalMs]);

  return { health, link, latency, error, refresh: check };
}
