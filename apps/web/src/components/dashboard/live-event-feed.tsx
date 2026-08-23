"use client";

import { Panel, SectionHeader, cx } from "./ui";

export type SimulationEvent = { id: string; cycle: number; type: string; customer_id: string | null; invoice_id: string | null; case_id: string | null; metadata: Record<string, string>; occurred_at: string };

const tone = (type: string) => type.includes("PAYMENT") ? "border-emerald-400 text-emerald-200" : type.includes("PROMISE") ? "border-rose-400 text-rose-200" : type.includes("DISPUTE") ? "border-amber-300 text-amber-200" : "border-sky-400 text-sky-200";
const label = (type: string) => type.replaceAll("_", " ");

export function LiveEventFeed({ events, customers }: { events: SimulationEvent[]; customers: Map<string, string> }) {
  return (
    <Panel>
      <SectionHeader
        eyebrow="Live recovery stream"
        title="Operational events"
        action={<span className="text-[10px] font-semibold uppercase tracking-[.13em] text-slate-500">{events.length} latest</span>}
      />
      <div className="max-h-[410px] space-y-1 overflow-y-auto p-3 pr-2">
        {events.length ? events.map((event) => (
          <article key={event.id} className={cx("live-enter border-l-2 px-3 py-3", tone(event.type))}>
            <div className="flex justify-between gap-3">
              <p className="text-xs font-bold">{label(event.type)}</p>
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
