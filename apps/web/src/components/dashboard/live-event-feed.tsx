"use client";

import { useMemo, useState } from "react";
import { Panel, SectionHeader, cx } from "./ui";
import type { SimulationEvent } from "./data";

export type { SimulationEvent } from "./data";

const tone = (type: string) => type.includes("PAYMENT") ? "border-emerald-400 text-emerald-200" : type.includes("PROMISE") ? "border-rose-400 text-rose-200" : type.includes("DISPUTE") ? "border-amber-300 text-amber-200" : "border-sky-400 text-sky-200";
const label = (type: string) => type.replaceAll("_", " ");

export function LiveEventFeed({ events, customers, onOpenCase }: { events: SimulationEvent[]; customers: Map<string, string>; onOpenCase?: (caseId: string) => void }) {
  const [order, setOrder] = useState<"newest" | "oldest">("newest");
  const orderedEvents = useMemo(() => [...events].sort((left, right) => {
    const time = new Date(left.occurred_at).getTime() - new Date(right.occurred_at).getTime();
    const comparison = time || left.cycle - right.cycle;
    return order === "newest" ? -comparison : comparison;
  }), [events, order]);

  return (
    <Panel className="overflow-hidden">
      <SectionHeader
        eyebrow="Recent portfolio changes"
        title="Live recovery stream"
        detail="Factual changes surfaced by recent simulation cycles—not a complete invoice archive."
        prominent
        action={<div className="flex rounded-lg border border-white/[.08] bg-black/10 p-1" aria-label="Operational event order">
          {(["newest", "oldest"] as const).map((value) => <button key={value} type="button" aria-pressed={order === value} onClick={() => setOrder(value)} className={cx("rounded-md px-2.5 py-1.5 text-[10px] font-semibold transition", order === value ? "bg-sky-300 text-slate-950" : "text-slate-400 hover:text-white")}>{value === "newest" ? "Newest first" : "Oldest first"}</button>)}
        </div>}
      />
      <div className="operational-scrollbar max-h-[22rem] overflow-y-auto overscroll-contain p-2.5 pr-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-sky-300/35 sm:max-h-[34rem]" role="region" aria-label={`Operational events, ${order} first`} tabIndex={0}>
        {orderedEvents.length ? orderedEvents.map((event, index) => (
          <article key={event.id} className={cx("live-enter border-l-2 px-3 py-2.5", tone(event.type), index === 0 && order === "newest" && "bg-sky-300/[.045]")}>
            <div className="flex justify-between gap-3">
              <p className="text-[11px] font-bold">{label(event.type)}{index === 0 && order === "newest" && <span className="ml-2 text-[8px] uppercase tracking-[.12em] text-sky-200">Latest</span>}</p>
              <span className="text-[9px] opacity-60">Cycle {event.cycle}</span>
            </div>
            <p className="mt-1 text-[10px] text-slate-300">
              {customers.get(event.customer_id ?? "") ?? "Portfolio account"} / {event.metadata.payment_amount ? `INR ${event.metadata.payment_amount} received` : event.metadata.promise_amount ? `INR ${event.metadata.promise_amount} commitment` : event.metadata.resulting_status ?? "Factual portfolio update"}
            </p>
            <p className="mt-0.5 text-[9px] text-slate-600">{new Date(event.occurred_at).toLocaleString()}</p>
            {event.case_id && onOpenCase && <button type="button" onClick={() => onOpenCase(event.case_id!)} className="mt-2 text-[10px] font-semibold text-sky-200 transition hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300/40">Open affected case →</button>}
          </article>
        )) : <p className="py-8 text-center text-xs text-slate-500">No simulation events yet.</p>}
      </div>
    </Panel>
  );
}
