"use client";

import { useEffect, useState } from "react";
import { apiBaseUrl, apiUrl } from "@/lib/api";

type HealthState = "checking" | "healthy" | "unavailable";

export function ApiHealth() {
  const [state, setState] = useState<HealthState>("checking");

  useEffect(() => {
    const controller = new AbortController();
    async function checkApiHealth() {
      try {
        const response = await fetch(apiUrl("/health"), { signal: controller.signal });
        const payload: unknown = await response.json();
        const isHealthy = response.ok && typeof payload === "object" && payload !== null &&
          "status" in payload && payload.status === "ok";
        setState(isHealthy ? "healthy" : "unavailable");
      } catch {
        if (!controller.signal.aborted) setState("unavailable");
      }
    }
    checkApiHealth();
    return () => controller.abort();
  }, []);

  const status = {
    checking: { label: "Checking API connection", color: "bg-amber-400" },
    healthy: { label: "API connected", color: "bg-emerald-400" },
    unavailable: { label: "API unavailable", color: "bg-rose-400" },
  }[state];

  return (
    <div className="flex items-center gap-3 border border-white/[.08] bg-slate-950/45 px-4 py-3 text-sm text-slate-300">
      <span className={`h-2.5 w-2.5 ${status.color}`} aria-hidden="true" />
      <span>{status.label}</span>
      <span className="ml-auto truncate text-xs text-slate-500">{apiBaseUrl ? `${apiBaseUrl}/health` : "API URL not configured"}</span>
    </div>
  );
}
