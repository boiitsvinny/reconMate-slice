"use client";

import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";

type InsightMode = { enabled: boolean; toggle: () => void };
const InsightModeContext = createContext<InsightMode | null>(null);
const STORAGE_KEY = "reconmate.intelligence-inspection";

export function InsightModeProvider({ children }: { children: ReactNode }) {
  const [enabled, setEnabled] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    setEnabled(window.sessionStorage.getItem(STORAGE_KEY) === "enabled");
  }, []);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 3_000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const value = useMemo(() => ({
    enabled,
    toggle: () => setEnabled((current) => {
      const next = !current;
      window.sessionStorage.setItem(STORAGE_KEY, next ? "enabled" : "disabled");
      setNotice(next ? "Intelligence Inspection enabled" : "Intelligence Inspection disabled");
      return next;
    }),
  }), [enabled]);

  return <InsightModeContext.Provider value={value}>{children}{notice && <div className="fixed right-4 top-20 z-[60] max-w-xs rounded-xl border border-sky-300/25 bg-[#0b1b31]/95 px-4 py-3 text-xs font-semibold text-sky-100 shadow-xl shadow-black/30 backdrop-blur" role="status" aria-live="polite">{notice}</div>}</InsightModeContext.Provider>;
}

export function useInsightMode() {
  const value = useContext(InsightModeContext);
  if (!value) throw new Error("useInsightMode must be used within InsightModeProvider.");
  return value;
}
