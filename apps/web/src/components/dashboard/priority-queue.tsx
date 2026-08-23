"use client";

import { useState } from "react";
import { CustomerPreview } from "./customer-preview";
import type { PriorityCase } from "./dashboard";

const statusClass = (state: string) => state === "ESCALATED" ? "bg-rose-400/10 text-rose-300 ring-rose-300/20" : state === "AWAITING_CUSTOMER" ? "bg-amber-400/10 text-amber-200 ring-amber-300/20" : "bg-sky-400/10 text-sky-300 ring-sky-300/20";

export function PriorityQueue({ items, onSelect, changedCaseIds }: { items: PriorityCase[]; onSelect: (item: PriorityCase) => void; changedCaseIds: Set<string> }) {
  const [hovered, setHovered] = useState<string | null>(null);
  return <section className="relative border border-white/[.09] bg-[#0d1627] p-4 shadow-[0_18px_45px_rgba(0,0,0,.16)] sm:p-5">
    <div className="mb-4 flex items-end justify-between gap-4 border-b border-white/[.07] pb-4"><div><p className="text-[10px] font-bold uppercase tracking-[.18em] text-sky-300">Deterministic queue</p><p className="mt-1 text-sm font-semibold text-white">Priority recovery work</p><p className="mt-1 text-xs text-slate-500">Factual state, recommendation eligibility, operator controlled.</p></div><span className="border border-white/[.08] px-2.5 py-1 text-[10px] font-medium text-slate-400">{items.length} active</span></div>
    <div className="hidden grid-cols-[minmax(180px,1.6fr)_0.8fr_0.7fr_0.9fr] gap-4 px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-600 md:grid"><span>Account</span><span>Exposure</span><span>Signal</span><span>Recovery state</span></div>
    <div className="min-h-[430px] space-y-1">
      {items.map((item) => <button type="button" key={item.id} onMouseEnter={() => setHovered(item.id)} onMouseLeave={() => setHovered(null)} onClick={() => onSelect(item)} className={`group relative grid w-full grid-cols-1 gap-2 rounded-xl border px-3 py-3 text-left transition hover:border-sky-300/15 hover:bg-sky-400/[0.045] md:grid-cols-[minmax(180px,1.6fr)_0.8fr_0.7fr_0.9fr] md:items-center md:gap-4 ${changedCaseIds.has(item.id) ? "live-enter border-sky-300/35 bg-sky-400/[.055]" : "border-transparent"}`}>
        <div><p className="text-sm font-medium text-slate-200 transition group-hover:text-white">{item.customerName}</p><p className="mt-0.5 text-[11px] text-slate-500">{item.customerReference}</p></div>
        <p className="text-sm font-semibold text-white">{item.amount}</p>
        <div><p className={`text-xs font-bold ${item.daysOverdue > 0 ? "text-rose-300" : "text-sky-300"}`}>{item.daysOverdue > 0 ? `${item.daysOverdue}D OVERDUE` : item.promiseSignal.toUpperCase()}</p><p className="mt-1 text-[10px] text-slate-500">{item.allowed ? "Recovery eligible" : item.reason}</p></div>
        <div className="flex items-center justify-between gap-2"><span className={`inline-flex w-fit rounded-full px-2 py-1 text-[10px] font-bold tracking-[0.08em] ring-1 ${statusClass(item.state)}`}>{item.state.replaceAll("_", " ")}</span><span className="text-slate-600 transition group-hover:translate-x-0.5 group-hover:text-sky-300">→</span></div>
        {hovered === item.id && <CustomerPreview item={item} />}
      </button>)}
    </div>
  </section>;
}
