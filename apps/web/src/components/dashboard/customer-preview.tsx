"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { PriorityCase } from "./data";
import { buttonStyles, StatusPill } from "./ui";

const toneForState = (state: string) => state === "ESCALATED" ? "rose" : state === "AWAITING_CUSTOMER" ? "amber" : "sky";

export type CasePreviewState = { item: PriorityCase; x: number; y: number };

export function useCasePreview() {
  const [preview, setPreview] = useState<CasePreviewState | null>(null);
  const pointer = useRef({ x: 24, y: 120 });

  useEffect(() => {
    const rememberPointer = (event: PointerEvent) => { pointer.current = { x: event.clientX, y: event.clientY }; };
    window.addEventListener("pointerdown", rememberPointer, true);
    return () => window.removeEventListener("pointerdown", rememberPointer, true);
  }, []);

  const openPreview = useCallback((item: PriorityCase) => {
    setPreview({ item, ...pointer.current });
  }, []);
  const closePreview = useCallback(() => setPreview(null), []);

  return { preview, openPreview, closePreview };
}

export function CustomerPreview({ preview, onClose, onViewMore }: { preview: CasePreviewState | null; onClose: () => void; onViewMore: (item: PriorityCase) => void }) {
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!preview) return;
    const dismiss = (event: PointerEvent) => {
      if (!cardRef.current?.contains(event.target as Node)) onClose();
    };
    const dismissOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("pointerdown", dismiss);
    document.addEventListener("keydown", dismissOnEscape);
    return () => {
      document.removeEventListener("pointerdown", dismiss);
      document.removeEventListener("keydown", dismissOnEscape);
    };
  }, [onClose, preview]);

  if (!preview) return null;
  const { item } = preview;
  const viewportWidth = typeof window === "undefined" ? 1280 : window.innerWidth;
  const viewportHeight = typeof window === "undefined" ? 800 : window.innerHeight;
  const width = Math.min(320, viewportWidth - 24);
  const left = viewportWidth < 640
    ? 12
    : Math.max(12, Math.min(preview.x + 16 + width <= viewportWidth ? preview.x + 16 : preview.x - width - 16, viewportWidth - width - 12));
  const top = Math.max(12, Math.min(preview.y - 28, viewportHeight - 330));

  return (
    <div ref={cardRef} style={{ left, top, width }} className="fixed z-[60] max-h-[calc(100vh-24px)] overflow-y-auto rounded-2xl border border-sky-300/20 bg-[#111a2d]/95 p-4 shadow-2xl shadow-black/70 backdrop-blur-2xl" role="dialog" aria-label={`${item.customerName} case preview`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-white">{item.customerName}</p>
          <p className="mt-0.5 text-[10px] uppercase tracking-[0.13em] text-slate-500">Case preview / {item.customerReference}</p>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill tone={toneForState(item.state)}>{item.state.replaceAll("_", " ")}</StatusPill>
          <button type="button" onClick={onClose} className="rounded-md px-1.5 py-0.5 text-xs text-slate-500 transition hover:bg-white/[.06] hover:text-white" aria-label="Close case preview">×</button>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 border-y border-white/[0.07] py-3">
        <div>
          <p className="text-[10px] uppercase tracking-[0.1em] text-slate-500">Outstanding</p>
          <p className="mt-1 text-base font-semibold text-white">{item.amount}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-[0.1em] text-slate-500">Eligibility</p>
          <p className={`mt-1 text-sm font-semibold ${item.allowed ? "text-emerald-300" : "text-amber-200"}`}>{item.allowed ? "Eligible" : "Blocked"}</p>
        </div>
      </div>
      <ul className="mt-3 space-y-1.5 text-xs leading-5 text-slate-400">
        <li className="font-medium text-sky-200">Next: {item.recommendedAction.replaceAll("_", " ")}</li>
        <li>{item.daysOverdue > 0 ? `${item.daysOverdue} days overdue` : "Current invoice exposure"}</li>
        <li>{item.promiseSignal}</li>
        <li className={item.allowed ? "text-emerald-300" : "text-amber-200"}>{item.reason}</li>
      </ul>
      <button type="button" onClick={() => onViewMore(item)} className={`${buttonStyles.primary} mt-4 w-full`}>{item.recommendedAction === "NO_ACTION_REQUIRED" ? "Inspect case" : "Review recommended action"}</button>
    </div>
  );
}
