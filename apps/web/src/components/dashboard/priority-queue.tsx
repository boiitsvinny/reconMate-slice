"use client";

import { useState } from "react";
import { CustomerPreview } from "./customer-preview";
import type { PriorityCase } from "./data";
import { cx, Panel, SectionHeader, StatusPill } from "./ui";

const stateTone = (state: string) => state === "ESCALATED" ? "rose" : state === "AWAITING_CUSTOMER" ? "amber" : state === "RESOLVED" ? "emerald" : "sky";

export function PriorityQueue({ items, onSelect, changedCaseIds }: { items: PriorityCase[]; onSelect: (item: PriorityCase) => void; changedCaseIds: Set<string> }) {
  const [hovered, setHovered] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const focusItems = items.filter((item) => item.recommendationPriority !== "LOW" && item.recommendedAction !== "NO_ACTION_REQUIRED");
  const visibleItems = showAll ? items : focusItems;

  return (
    <Panel className="relative">
      <SectionHeader
        eyebrow="Act now"
        title="Prioritized recovery work"
        detail="Ordered by the API recommendation priority, overdue age and exposure."
        action={
          <div className="flex rounded-xl border border-white/[.08] p-0.5 text-[10px] font-semibold uppercase tracking-[.08em]">
            <button type="button" onClick={() => setShowAll(false)} className={cx("px-2.5 py-1.5 transition", !showAll ? "bg-sky-300 text-slate-950" : "text-slate-500 hover:text-white")}>Focus {focusItems.length}</button>
            <button type="button" onClick={() => setShowAll(true)} className={cx("px-2.5 py-1.5 transition", showAll ? "bg-sky-300 text-slate-950" : "text-slate-500 hover:text-white")}>All {items.length}</button>
          </div>
        }
      />
      <div className="hidden grid-cols-[minmax(180px,1.6fr)_0.8fr_0.7fr_0.9fr] gap-4 px-5 pb-2 pt-4 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-600 md:grid">
        <span>Account</span>
        <span>Exposure</span>
        <span>Next step</span>
        <span>Recovery state</span>
      </div>
      <div className="min-h-[430px] space-y-1 p-3 pt-0 sm:p-4 sm:pt-0">
        {visibleItems.map((item, index) => (
          <button
            type="button"
            key={item.id}
            onMouseEnter={() => setHovered(item.id)}
            onMouseLeave={() => setHovered(null)}
            onClick={() => onSelect(item)}
            className={cx(
              "group relative grid w-full grid-cols-1 gap-2 rounded-xl border px-3 py-3 text-left transition hover:border-sky-300/20 hover:bg-sky-400/[0.045] md:grid-cols-[minmax(180px,1.6fr)_0.8fr_0.7fr_0.9fr] md:items-center md:gap-4",
              changedCaseIds.has(item.id) ? "live-enter border-sky-300/35 bg-sky-400/[.055]" : "border-transparent",
            )}
          >
            <div>
              <div className="flex items-center gap-2">
                <span className="w-4 text-[10px] tabular-nums text-slate-600">{String(index + 1).padStart(2, "0")}</span>
                <p className="truncate text-sm font-medium text-slate-200 transition group-hover:text-white">{item.customerName}</p>
              </div>
              <p className="mt-0.5 pl-6 text-[11px] text-slate-500">{item.customerReference}</p>
            </div>
            <div>
              <p className="text-sm font-semibold tabular-nums text-white">{item.amount}</p>
              <p className={cx("mt-1 text-[10px] font-semibold uppercase", item.daysOverdue > 0 ? "text-rose-300" : "text-slate-500")}>{item.daysOverdue > 0 ? `${item.daysOverdue}D overdue` : "Not overdue"}</p>
            </div>
            <div className="min-w-0">
              <p className="truncate text-xs font-semibold text-sky-200">{item.recommendedAction.replaceAll("_", " ")}</p>
              <p className="mt-1 truncate text-[10px] text-slate-500">{item.humanApprovalRequired ? "Approval required" : item.promiseSignal}</p>
            </div>
            <div className="flex items-center justify-between gap-2">
              <StatusPill tone={stateTone(item.state)}>{item.state.replaceAll("_", " ")}</StatusPill>
              <span className="text-slate-600 transition group-hover:translate-x-0.5 group-hover:text-sky-300">View</span>
            </div>
            {hovered === item.id && <CustomerPreview item={item} />}
          </button>
        ))}
        {!visibleItems.length && (
          <div className="grid min-h-[360px] place-items-center px-6 text-center">
            <div><p className="text-sm font-medium text-slate-300">No cases require immediate action</p><p className="mt-2 text-xs text-slate-500">Open All to review monitored and resolved recovery cases.</p></div>
          </div>
        )}
      </div>
    </Panel>
  );
}
