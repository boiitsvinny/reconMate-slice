"use client";

import { Panel, SectionHeader, cx } from "./ui";
import type { SimulationEvent } from "./data";

export type { SimulationEvent } from "./data";

const tone = (type: string) => type.includes("PAYMENT") ? "border-emerald-400 text-emerald-200" : type.includes("PROMISE") ? "border-rose-400 text-rose-200" : type.includes("DISPUTE") ? "border-amber-300 text-amber-200" : "border-sky-400 text-sky-200";
const label = (type: string) => type.replaceAll("_", " ");

export function LiveEventFeed({ events, customers }: { events: SimulationEvent[]; customers: Map<string, string> }) {
  return (
    <Panel className="overflow-hidden">
      <SectionHeader
        eyebrow="Live recovery stream"
        title="Operational events"
        action={<span className="text-[10px] font-semibold uppercase tracking-[.13em] text-slate-500">{events.length} events / newest first</span>}
      />
      <div className="operational-scrollbar max-h-[22rem] space-y-1 overflow-y-auto overscroll-contain p-3 pr-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-sky-300/35 sm:max-h-[34rem]" role="region" aria-label="Operational events, newest first" tabIndex={0}>
        {events.length ? events.map((event, index) => (
          <article key={event.id} className={cx("live-enter border-l-2 px-3 py-3", tone(event.type), index === 0 && "bg-sky-300/[.045]")}>
            <div className="flex justify-between gap-3">
              <p className="text-xs font-bold">{label(event.type)}{index === 0 && <span className="ml-2 text-[9px] uppercase tracking-[.12em] text-sky-200">Latest</span>}</p>
              <span className="text-[10px] opacity-60">#{event.cycle}</span>
            </div>
            <p className="mt-1 text-[11px] text-slate-300">
              {customers.get(event.customer_id ?? "") ?? "Portfolio account"} / {event.metadata.payment_amount ? `INR ${event.metadata.payment_amount} received` : event.metadata.promise_amount ? `INR ${event.metadata.promise_amount} commitment` : event.metadata.resulting_status ?? "Factual portfolio update"}
            </p>
            <p className="mt-1 text-[10px] text-slate-500">{new Date(event.occurred_at).toLocaleString()}</p>
          </article>
        )) : <p className="py-8 text-center text-xs text-slate-500">No simulation events yet.</p>}
      </div>
    </Panel>
  );
}
