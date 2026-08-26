"use client";

import Link from "next/link";
import type { IntelligenceResult, PortfolioIntelligence } from "@/lib/intelligence-api";
import type { IntelligenceTransition, PriorityCase } from "./data";
import { formatMoney } from "./data";
import { buttonStyles, Panel, SectionHeader, StatusPill } from "./ui";

type Props = {
  intelligence?: PortfolioIntelligence;
  loading: boolean;
  error: string | null;
  transitions: IntelligenceTransition[];
  casesByCustomer: Map<string, PriorityCase>;
  caseLinksLoading: boolean;
  caseLinksError: boolean;
  onSelectCase: (item: PriorityCase) => void;
};

const isRestraint = (item: IntelligenceResult) => item.recommendation.action === "MONITOR" || item.recommendation.action === "WAIT_FOR_PROMISE";
const riskTone = (level: IntelligenceResult["level"]) => level === "CRITICAL" ? "rose" : level === "HIGH" ? "amber" : level === "MEDIUM" ? "sky" : "slate";
const decisionLabel = (value: string) => value.replaceAll("_", " ");

export function AIPriorities({ intelligence, loading, error, transitions, casesByCustomer, caseLinksLoading, caseLinksError, onSelectCase }: Props) {
  if (loading) return <Panel className="mt-5 h-72 animate-pulse bg-white/[.035]"><span className="sr-only">Loading AI priorities</span></Panel>;
  if (!intelligence) return <Panel className="mt-5 overflow-hidden border-amber-300/15"><SectionHeader eyebrow="Contextual decisioning" title="AI priorities are temporarily unavailable" detail={error ?? "Current customer intelligence could not be evaluated."} prominent /></Panel>;

  const customers = new Map(intelligence.customers.map((item) => [item.entity_id, item]));
  const materialTransitions = transitions.filter((item) => item.entity_type === "CUSTOMER" && item.material);
  const changedPriority = materialTransitions.map((transition) => ({ item: customers.get(transition.entity_id), transition })).find(({ item }) => item && !isRestraint(item));
  const urgent = changedPriority?.item ?? intelligence.highest_priority.find((item) => !isRestraint(item));
  const urgentTransition = changedPriority?.item?.entity_id === urgent?.entity_id ? changedPriority?.transition : materialTransitions.find((item) => item.entity_id === urgent?.entity_id);
  const restraint = [...intelligence.customers]
    .filter((item) => isRestraint(item) && item.entity_id !== urgent?.entity_id)
    .sort((left, right) => Number(right.metrics.overdue_exposure) - Number(left.metrics.overdue_exposure))[0];
  const restraintTransition = materialTransitions.find((item) => item.entity_id === restraint?.entity_id);

  return (
    <Panel className="mt-5 overflow-hidden">
      <SectionHeader eyebrow="Contextual decisioning" title="AI Priorities" detail="The same overdue condition can produce a different decision when customer evidence differs." prominent />
      {caseLinksError && <p className="border-b border-amber-300/10 bg-amber-300/[.04] px-5 py-3 text-[11px] text-amber-100/75">Case links are temporarily unavailable; the current decision evidence remains visible.</p>}
      <div className="grid gap-px bg-white/[.06] xl:grid-cols-2">
        {urgent && <PriorityDecisionCard kind="priority" item={urgent} transition={urgentTransition} recoveryCase={casesByCustomer.get(urgent.entity_id)} caseLinkLoading={caseLinksLoading} onSelectCase={onSelectCase} />}
        {restraint && <PriorityDecisionCard kind="restraint" item={restraint} transition={restraintTransition} recoveryCase={casesByCustomer.get(restraint.entity_id)} caseLinkLoading={caseLinksLoading} onSelectCase={onSelectCase} />}
      </div>
    </Panel>
  );
}

function PriorityDecisionCard({ kind, item, transition, recoveryCase, caseLinkLoading, onSelectCase }: { kind: "priority" | "restraint"; item: IntelligenceResult; transition?: IntelligenceTransition; recoveryCase?: PriorityCase; caseLinkLoading: boolean; onSelectCase: (item: PriorityCase) => void }) {
  const restraint = kind === "restraint";
  const evidence = [
    item.metrics.broken_promise_count ? `${item.metrics.broken_promise_count} broken promise${item.metrics.broken_promise_count === 1 ? "" : "s"}` : null,
    item.metrics.active_promise_count ? `${item.metrics.active_promise_count} active promise${item.metrics.active_promise_count === 1 ? "" : "s"}` : null,
    item.metrics.active_dispute_count ? `${item.metrics.active_dispute_count} active dispute${item.metrics.active_dispute_count === 1 ? "" : "s"}` : null,
    item.metrics.max_days_overdue ? `${item.metrics.max_days_overdue} days overdue` : null,
    item.metrics.days_since_last_payment === null ? "No payment recorded" : `Payment ${item.metrics.days_since_last_payment} days ago`,
  ].filter((value): value is string => Boolean(value)).slice(0, 4);
  const currentDecision = transition?.current_recommendation_title ?? item.recommendation.title;
  const previousDecision = transition?.previous_recommendation ? decisionLabel(transition.previous_recommendation) : null;
  const reason = transition?.why_intelligence_changed || item.recommendation.explanation;

  return (
    <article className={`relative bg-[#08111f] p-5 sm:p-7 ${restraint ? "border-t-[3px] border-t-emerald-300/50 xl:border-l xl:border-t-0" : "border-t-[3px] border-t-rose-300/60"}`}>
      <p className={`mb-4 text-sm font-extrabold uppercase tracking-[.18em] ${restraint ? "text-emerald-200" : "text-rose-200"}`}>{restraint ? "Do not act yet" : "Act now"}</p>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><p className={`text-[11px] font-bold uppercase tracking-[.14em] ${restraint ? "text-emerald-300" : "text-rose-300"}`}>{restraint ? "Intelligent restraint" : transition ? "Decision changed" : "Operator priority"}</p><h3 className="mt-2 text-2xl font-semibold text-white">{item.entity_name}</h3><p className="mt-1 text-[15px] font-medium tabular-nums text-slate-300">{formatMoney(item.metrics.total_outstanding_amount)} outstanding</p></div>
        <StatusPill tone={riskTone(item.level)}>{item.level} · {item.score}/100</StatusPill>
      </div>

      <div className={`mt-5 rounded-xl border p-4 ${restraint ? "border-emerald-300/15 bg-emerald-300/[.035]" : "border-sky-300/15 bg-sky-300/[.035]"}`}>
        <p className="text-[10px] font-bold uppercase tracking-[.13em] text-slate-400">Recovery decision</p>
        {previousDecision ? <div className="mt-3 flex flex-wrap items-center gap-3 text-base font-semibold"><span className="text-slate-500 line-through decoration-slate-500/50">{previousDecision}</span><span className="text-lg text-sky-300">→</span><span className={restraint ? "text-emerald-200" : "text-white"}>{currentDecision}</span></div> : <p className={`mt-2 text-lg font-semibold ${restraint ? "text-emerald-200" : "text-white"}`}>{currentDecision}</p>}
        {transition?.previous_score !== null && transition?.previous_score !== undefined ? <p className="mt-3 text-[13px] text-slate-400">Current Intelligence Score <span className="tabular-nums text-slate-500">{transition.previous_score}</span> <span className="mx-1.5 text-sky-300">→</span> <span className="text-base font-semibold tabular-nums text-white">{transition.current_score}</span></p> : <p className="mt-3 text-[13px] text-slate-400">Current Intelligence Score: <strong className="text-white">{item.score}/100</strong></p>}
      </div>

      <div className="mt-4">
        <p className="text-[10px] font-bold uppercase tracking-[.13em] text-slate-400">{transition ? "What changed" : "Why this decision"}</p>
        <p className="mt-2 text-[13px] leading-6 text-slate-200">{reason}</p>
        {restraint && <p className="mt-2 text-[13px] leading-6 text-emerald-100/80">ReconMate is deliberately holding additional recovery action while the current evidence supports monitoring or the active promise.</p>}
      </div>

      <div className="mt-4 flex flex-wrap gap-2" aria-label="Decision evidence">{evidence.map((value) => <span key={value} className="rounded-full border border-white/[.1] bg-white/[.03] px-3 py-1.5 text-xs text-slate-300">{value}</span>)}</div>
      <div className="mt-5">
        {caseLinkLoading ? <button type="button" disabled className={buttonStyles.secondary}>Connecting decision…</button> : recoveryCase ? <button type="button" onClick={() => onSelectCase(recoveryCase)} className={restraint ? buttonStyles.secondary : buttonStyles.primary}>View decision</button> : <Link href="/analytics" className={buttonStyles.secondary}>Analyze decision</Link>}
      </div>
    </article>
  );
}
