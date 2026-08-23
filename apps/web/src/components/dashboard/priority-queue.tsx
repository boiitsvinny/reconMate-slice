"use client";

import { useState } from "react";
import { CustomerPreview } from "./customer-preview";
import type { PriorityCase } from "./dashboard";
import { cx, Panel, SectionHeader, StatusPill } from "./ui";

const stateTone = (state: string) => state === "ESCALATED" ? "rose" : state === "AWAITING_CUSTOMER" ? "amber" : "sky";

export function PriorityQueue({ items, onSelect, changedCaseIds }: { items: PriorityCase[]; onSelect: (item: PriorityCase) => void; changedCaseIds: Set<string> }) {
  const [hovered, setHovered] = useState<string | null>(null);

  return (
    <Panel className="relative">
      <SectionHeader
        eyebrow="Deterministic queue"
        title="Priority recovery work"
        detail="Factual state, recommendation eligibility, operator controlled."
        action={<span className="border border-white/[.08] px-2.5 py-1 text-[10px] font-medium text-slate-400">{items.length} active</span>}
      />
      <div className="hidden grid-cols-[minmax(180px,1.6fr)_0.8fr_0.7fr_0.9fr] gap-4 px-5 pb-2 pt-4 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-600 md:grid">
        <span>Account</span>
        <span>Exposure</span>
        <span>Signal</span>
        <span>Recovery state</span>
      </div>
      <div className="min-h-[430px] space-y-1 p-3 pt-0 sm:p-4 sm:pt-0">
        {items.map((item) => (
          <button
            type="button"
            key={item.id}
            onMouseEnter={() => setHovered(item.id)}
            onMouseLeave={() => setHovered(null)}
            onClick={() => onSelect(item)}
            className={cx(
              "group relative grid w-full grid-cols-1 gap-2 border px-3 py-3 text-left transition hover:border-sky-300/20 hover:bg-sky-400/[0.045] md:grid-cols-[minmax(180px,1.6fr)_0.8fr_0.7fr_0.9fr] md:items-center md:gap-4",
              changedCaseIds.has(item.id) ? "live-enter border-sky-300/35 bg-sky-400/[.055]" : "border-transparent",
            )}
          >
            <div>
              <p className="text-sm font-medium text-slate-200 transition group-hover:text-white">{item.customerName}</p>
              <p className="mt-0.5 text-[11px] text-slate-500">{item.customerReference}</p>
            </div>
            <p className="text-sm font-semibold tabular-nums text-white">{item.amount}</p>
            <div>
              <p className={cx("text-xs font-bold uppercase", item.daysOverdue > 0 ? "text-rose-300" : "text-sky-300")}>
                {item.daysOverdue > 0 ? `${item.daysOverdue}D overdue` : item.promiseSignal}
              </p>
              <p className="mt-1 truncate text-[10px] text-slate-500">{item.allowed ? "Recovery eligible" : item.reason}</p>
            </div>
            <div className="flex items-center justify-between gap-2">
              <StatusPill tone={stateTone(item.state)}>{item.state.replaceAll("_", " ")}</StatusPill>
              <span className="text-slate-600 transition group-hover:translate-x-0.5 group-hover:text-sky-300">View</span>
            </div>
            {hovered === item.id && <CustomerPreview item={item} />}
          </button>
        ))}
      </div>
    </Panel>
  );
}
