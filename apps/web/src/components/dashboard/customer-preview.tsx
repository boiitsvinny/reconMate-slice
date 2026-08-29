"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { PriorityCase } from "./data";
import { buttonStyles, StatusPill } from "./ui";

const toneForRisk = (risk: PriorityCase["currentRisk"]) => risk === "CRITICAL" ? "rose" : risk === "HIGH" ? "amber" : "sky";

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
  const [position, setPosition] = useState<{ left: number; top: number; width: number } | null>(null);

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

  useLayoutEffect(() => {
    if (!preview || !cardRef.current) {
      setPosition(null);
      return;
    }
    const placeBesidePointer = () => {
      const edge = 12;
      const gap = 14;
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;
      const width = Math.min(320, viewportWidth - edge * 2);
      const height = Math.min(cardRef.current?.scrollHeight ?? 0, viewportHeight - edge * 2);
      const preferredLeft = preview.x + gap;
      const preferredTop = preview.y + gap;
      const left = Math.max(edge, Math.min(preferredLeft + width <= viewportWidth - edge ? preferredLeft : preview.x - width - gap, viewportWidth - width - edge));
      const top = Math.max(edge, Math.min(preferredTop + height <= viewportHeight - edge ? preferredTop : preview.y - height - gap, viewportHeight - height - edge));
      setPosition({ left, top, width });
    };
    placeBesidePointer();
    window.addEventListener("resize", placeBesidePointer);
    return () => window.removeEventListener("resize", placeBesidePointer);
  }, [preview]);

  if (!preview) return null;
  const { item } = preview;
  const recoveryComplete = item.recommendedAction === "NO_ACTION_REQUIRED" || item.exposure <= 0 || item.state === "RESOLVED";

  return createPortal(
    <div ref={cardRef} style={{ left: position?.left ?? 12, top: position?.top ?? 12, width: position?.width ?? "min(320px, calc(100vw - 24px))", visibility: position ? "visible" : "hidden" }} className="fixed z-[60] max-h-[calc(100vh-24px)] overflow-x-hidden overflow-y-auto rounded-2xl border border-sky-300/20 bg-[#111a2d]/95 p-4 shadow-2xl shadow-black/70 backdrop-blur-2xl" role="dialog" aria-label={`${item.customerName} case preview`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-white">{item.customerName}</p>
          <p className="mt-0.5 text-[10px] uppercase tracking-[0.13em] text-slate-500">Case preview / {item.customerReference}</p>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill tone={toneForRisk(item.currentRisk)}>{item.currentRisk} · {item.currentScore}/100</StatusPill>
          <button type="button" onClick={onClose} className="rounded-md px-1.5 py-0.5 text-xs text-slate-500 transition hover:bg-white/[.06] hover:text-white" aria-label="Close case preview">×</button>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 border-y border-white/[0.07] py-3">
        <div>
          <p className="text-[10px] uppercase tracking-[0.1em] text-slate-500">Outstanding</p>
          <p className="mt-1 text-base font-semibold text-white">{item.amount}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-[0.1em] text-slate-500">Stored workflow state</p>
          <p className="mt-1 text-sm font-semibold text-slate-200">{item.state.replaceAll("_", " ")}</p>
        </div>
      </div>
      <ul className="mt-3 space-y-1.5 text-xs leading-5 text-slate-400">
        <li className={recoveryComplete ? "font-semibold text-emerald-200" : "font-medium text-sky-200"}>Current case decision: {recoveryComplete ? "RECOVERY COMPLETE / NO ACTION REQUIRED" : item.recommendedAction.replaceAll("_", " ")}</li>
        <li>Customer-level intelligence: {item.currentAction.replaceAll("_", " ")}</li>
        <li>{item.daysOverdue > 0 ? `${item.daysOverdue} days overdue` : "Current invoice exposure"}</li>
        <li>{item.promiseSignal}</li>
        <li className={item.allowed ? "text-emerald-300" : "text-amber-200"}>{item.reason}</li>
      </ul>
      <button type="button" onClick={() => onViewMore(item)} className={`${buttonStyles.primary} mt-4 w-full`}>{item.recommendedAction === "NO_ACTION_REQUIRED" ? "Inspect case" : "Review recommended action"}</button>
    </div>,
    document.body,
  );
}
