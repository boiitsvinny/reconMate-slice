"use client";

import { useEffect, useMemo, useState } from "react";
import type { PortfolioIntelligence } from "@/lib/intelligence-api";
import type { IntelligenceTransition, PriorityCase, SimulationEvent } from "./data";
import { cx, Panel, SectionHeader, StatusPill } from "./ui";

type QueueFilter = "PRIORITY" | "CHANGED" | "PROMISES" | "APPROVALS" | "DEVIATIONS" | "RISK" | "DISPUTES";

const filters: { key: QueueFilter; label: string }[] = [
  { key: "PRIORITY", label: "Priority" },
  { key: "CHANGED", label: "Changed decisions" },
  { key: "PROMISES", label: "Broken promises" },
  { key: "APPROVALS", label: "Approval required" },
  { key: "DEVIATIONS", label: "Behaviour deviations" },
  { key: "RISK", label: "High recovery risk" },
  { key: "DISPUTES", label: "Disputes" },
];

export function HomeRecoveryQueue({ items, intelligence, transitions, events, onSelect }: { items: PriorityCase[]; intelligence: PortfolioIntelligence; transitions: IntelligenceTransition[]; events: SimulationEvent[]; onSelect: (item: PriorityCase) => void }) {
  const [activeFilter, setActiveFilter] = useState<QueueFilter>(transitions.some((item) => item.material) ? "CHANGED" : "PRIORITY");
  const [filterSelected, setFilterSelected] = useState(false);
  useEffect(() => {
    if (!filterSelected && transitions.some((item) => item.material)) setActiveFilter("CHANGED");
  }, [filterSelected, transitions]);
  const intelligenceByCustomer = useMemo(() => new Map(intelligence.customers.map((item) => [item.entity_id, item])), [intelligence]);
  const transitionByCustomer = useMemo(() => new Map(transitions.filter((item) => item.entity_type === "CUSTOMER").map((item) => [item.entity_id, item])), [transitions]);
  const latestEventByCustomer = useMemo(() => {
    const map = new Map<string, SimulationEvent>();
    for (const event of [...events].sort((left, right) => new Date(right.occurred_at).getTime() - new Date(left.occurred_at).getTime())) if (event.customer_id && !map.has(event.customer_id)) map.set(event.customer_id, event);
    return map;
  }, [events]);
  const uniqueCases = useMemo(() => {
    const map = new Map<string, PriorityCase>();
    for (const item of items) if (!map.has(item.customerId) || item.recommendationPriority === "CRITICAL") map.set(item.customerId, item);
    return [...map.values()];
  }, [items]);
  const matches = (item: PriorityCase) => {
    const intel = intelligenceByCustomer.get(item.customerId);
    const transition = transitionByCustomer.get(item.customerId);
    if (activeFilter === "CHANGED") return Boolean(transition?.material);
    if (activeFilter === "PROMISES") return Boolean(intel?.metrics.broken_promise_count);
    if (activeFilter === "APPROVALS") return item.humanApprovalRequired;
    if (activeFilter === "DEVIATIONS") return Boolean(intel?.signals.some((signal) => signal.type === "PAYMENT_ACTIVITY_STALLED" || signal.type === "RECOVERY_STALLED"));
    if (activeFilter === "RISK") return intel?.level === "CRITICAL" || intel?.level === "HIGH";
    if (activeFilter === "DISPUTES") return Boolean(intel?.metrics.active_dispute_count);
    return item.recommendedAction !== "NO_ACTION_REQUIRED" && item.state !== "RESOLVED";
  };
  const visible = uniqueCases.filter(matches).sort((left, right) => {
    const leftScore = intelligenceByCustomer.get(left.customerId)?.score ?? 0;
    const rightScore = intelligenceByCustomer.get(right.customerId)?.score ?? 0;
    return rightScore - leftScore || right.exposure - left.exposure;
  }).slice(0, 12);

  return (
    <Panel className="mt-5 overflow-hidden">
      <SectionHeader eyebrow="Operational work" title="Recovery Queue" detail="Meaningful decisions and recovery signals—not a raw invoice register." prominent />
      <div className="hide-scrollbar flex gap-2 overflow-x-auto border-b border-white/[.06] px-4 py-3" aria-label="Recovery queue filters">{filters.map((filter) => <button key={filter.key} type="button" aria-pressed={activeFilter === filter.key} onClick={() => { setActiveFilter(filter.key); setFilterSelected(true); }} className={cx("whitespace-nowrap rounded-lg border px-3 py-2 text-[11px] font-semibold transition", activeFilter === filter.key ? "border-sky-300/35 bg-sky-300/[.1] text-sky-100" : "border-white/[.07] text-slate-400 hover:text-white")}>{filter.label}</button>)}</div>
      <div className="hidden grid-cols-[minmax(180px,1.1fr)_110px_minmax(190px,1.2fr)_minmax(190px,1.15fr)_110px] gap-4 border-b border-white/[.05] px-5 py-3 text-[11px] font-bold uppercase tracking-[.12em] text-slate-400 lg:grid"><span>Customer</span><span>Exposure</span><span>Decision</span><span>Important trigger</span><span>Status</span></div>
      <div className="operational-scrollbar max-h-[32rem] divide-y divide-white/[.055] overflow-x-hidden overflow-y-auto overscroll-contain bg-[#050914]/45" role="region" aria-label="Recovery queue records" tabIndex={0}>
        {visible.map((item) => {
          const intel = intelligenceByCustomer.get(item.customerId);
          const transition = transitionByCustomer.get(item.customerId);
          const event = latestEventByCustomer.get(item.customerId);
          const trigger = transition?.what_changed || intel?.signals[0]?.title || item.recommendationReason;
          const held = intel?.recommendation.action === "MONITOR" || intel?.recommendation.action === "WAIT_FOR_PROMISE";
          const status = item.humanApprovalRequired ? "Approval" : intel?.metrics.active_dispute_count ? "Blocked" : held ? "Monitoring" : "Ready";
          return <button type="button" key={item.customerId} onClick={() => onSelect(item)} className="interactive-row grid w-full gap-3 px-4 py-4 text-left lg:grid-cols-[minmax(180px,1.1fr)_110px_minmax(190px,1.2fr)_minmax(190px,1.15fr)_110px] lg:items-center lg:gap-4 lg:px-5"><div><p className="truncate text-sm font-semibold text-white">{item.customerName}</p><p className="mt-1 text-[11px] text-slate-500">{formatEvaluationTime(event?.occurred_at ?? intel?.calculated_at)}</p></div><div><p className="text-sm font-semibold tabular-nums text-slate-200">{item.amount}</p><p className="mt-1 text-xs text-slate-400">{item.daysOverdue}d overdue</p></div><div><p className="text-[13px] font-semibold leading-5 text-sky-200">{transition?.previous_recommendation ? `${transition.previous_recommendation.replaceAll("_", " ")} → ${transition.current_recommendation_title}` : intel?.recommendation.title ?? item.recommendedAction.replaceAll("_", " ")}</p>{intel && <p className="mt-1 text-xs tabular-nums text-slate-400">Score {transition?.previous_score !== null && transition?.previous_score !== undefined ? `${transition.previous_score} → ` : ""}{intel.score}/100</p>}</div><p className="line-clamp-2 text-[13px] leading-5 text-slate-300">{trigger}</p><StatusPill tone={status === "Approval" ? "amber" : status === "Blocked" ? "rose" : status === "Monitoring" ? "emerald" : "sky"}>{status}</StatusPill></button>;
        })}
        {!visible.length && <div className="px-6 py-12 text-center"><p className="text-sm font-semibold text-slate-300">No current records in this queue</p><p className="mt-2 text-xs text-slate-500">ReconMate applied this filter without substituting unrelated recovery work.</p></div>}
      </div>
    </Panel>
  );
}

function formatEvaluationTime(value?: string) {
  if (!value) return "Current evaluation";
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return "Current evaluation";
  return `Reassessed ${timestamp.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}`;
}
