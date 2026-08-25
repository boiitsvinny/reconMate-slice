"use client";

import Link from "next/link";
import type { IntelligenceResult, PortfolioIntelligence } from "@/lib/intelligence-api";
import type { PriorityCase } from "./data";
import { formatMoney } from "./data";
import { buttonStyles, cx, Panel, SectionHeader, StatusPill } from "./ui";

type Props = {
  intelligence?: PortfolioIntelligence;
  loading: boolean;
  error: string | null;
  casesByCustomer: Map<string, PriorityCase>;
  caseLinksLoading: boolean;
  caseLinksError: boolean;
  affectedCustomerIds: Set<string>;
  onSelectCase: (item: PriorityCase) => void;
  onRetry: () => void;
  onRetryCaseLinks: () => void;
};

type FocusLane = "urgent" | "review" | "waiting";

const laneFor = (action: string): FocusLane => {
  if (action === "REVIEW_DISPUTE") return "review";
  if (action === "WAIT_FOR_PROMISE" || action === "MONITOR") return "waiting";
  return "urgent";
};

const lanePresentation = {
  urgent: { label: "Action recommended", tone: "rose" as const, border: "border-l-rose-300/70" },
  review: { label: "Review required", tone: "amber" as const, border: "border-l-amber-300/70" },
  waiting: { label: "Blocked / waiting", tone: "slate" as const, border: "border-l-slate-400/60" },
};

const riskTone = (level: IntelligenceResult["level"]) => level === "CRITICAL" ? "rose" : level === "HIGH" ? "amber" : level === "MEDIUM" ? "sky" : "slate";

export function TodaysOperationalFocus({ intelligence, loading, error, casesByCustomer, caseLinksLoading, caseLinksError, affectedCustomerIds, onSelectCase, onRetry, onRetryCaseLinks }: Props) {
  const items = intelligence?.highest_priority.filter((item) => item.recommendation.action !== "MONITOR").slice(0, 5) ?? [];

  return (
    <Panel className="mt-7 overflow-hidden">
      <SectionHeader
        eyebrow="Today's operational focus"
        title="What needs attention right now"
        detail={intelligence ? "Backend-ranked accounts, presented in current intelligence priority order." : "Loading the current operational priority list."}
        prominent
      />
      {loading && <FocusLoading />}
      {!loading && error && !intelligence && (
        <div className="flex flex-col justify-between gap-4 p-6 sm:flex-row sm:items-center">
          <div><p className="text-sm font-semibold text-rose-100">Operational focus could not be evaluated</p><p className="mt-1 text-xs leading-5 text-slate-500">{error}</p></div>
          <button type="button" onClick={onRetry} className={buttonStyles.secondary}>Try intelligence again</button>
        </div>
      )}
      {intelligence && caseLinksError && <div className="flex flex-col justify-between gap-2 border-b border-amber-300/10 bg-amber-300/[.04] px-5 py-3 text-[11px] text-amber-100/75 sm:flex-row sm:items-center"><p>Case workspace links are temporarily unavailable. Intelligence review remains available.</p><button type="button" onClick={onRetryCaseLinks} className="font-semibold text-amber-100 underline decoration-amber-200/30 underline-offset-4">Retry case links</button></div>}
      {!loading && intelligence && !items.length && (
        <div className="px-6 py-12 text-center">
          <div className="mx-auto grid h-10 w-10 place-items-center rounded-full border border-emerald-300/20 bg-emerald-300/[.07] text-emerald-200">✓</div>
          <p className="mt-4 text-sm font-semibold text-slate-200">No urgent intelligence findings</p>
          <p className="mx-auto mt-2 max-w-lg text-xs leading-5 text-slate-500">Current recommendations indicate routine monitoring. The portfolio will be evaluated again on the next live refresh.</p>
        </div>
      )}
      {items.length > 0 && (
        <div className="divide-y divide-white/[.06]">
          {items.map((item, index) => <FocusItem key={item.entity_id} item={item} index={index} recoveryCase={casesByCustomer.get(item.entity_id)} caseLinkLoading={caseLinksLoading} affected={affectedCustomerIds.has(item.entity_id)} onSelectCase={onSelectCase} />)}
        </div>
      )}
    </Panel>
  );
}

function FocusItem({ item, index, recoveryCase, caseLinkLoading, affected, onSelectCase }: { item: IntelligenceResult; index: number; recoveryCase?: PriorityCase; caseLinkLoading: boolean; affected: boolean; onSelectCase: (item: PriorityCase) => void }) {
  const lane = laneFor(item.recommendation.action);
  const presentation = lanePresentation[lane];
  const signals = item.signals.slice(0, 2);

  return (
    <article className={cx("border-l-2 px-4 py-4 transition hover:bg-white/[.018] sm:px-5", presentation.border, affected && "live-enter bg-sky-300/[.035]")}> 
      <div className="grid gap-4 lg:grid-cols-[minmax(210px,.8fr)_minmax(360px,1.55fr)_auto] lg:items-center">
        <div className="min-w-0">
          <div className="flex items-center gap-2"><span className="text-[10px] tabular-nums text-slate-600">{String(index + 1).padStart(2, "0")}</span><h3 className="truncate text-sm font-semibold text-white">{item.entity_name}</h3></div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <StatusPill tone={riskTone(item.level)}>{item.level} / {item.score}</StatusPill>
            <StatusPill tone={presentation.tone}>{presentation.label}</StatusPill>
          </div>
          <p className="mt-2 text-[11px] text-slate-400">{formatMoney(item.metrics.overdue_exposure)} overdue / {item.metrics.max_days_overdue} days maximum</p>
          {recoveryCase && <p className="mt-1 text-[10px] text-slate-600">Case {recoveryCase.id.slice(0, 8)} / {recoveryCase.state.replaceAll("_", " ")}</p>}
        </div>
        <div className="min-w-0">
          <p className="text-[9px] font-bold uppercase tracking-[.13em] text-sky-300/70">Current recommendation</p>
          <p className="mt-1 text-sm font-semibold text-sky-100">{item.recommendation.title}</p>
          <p className="mt-1.5 text-xs leading-5 text-slate-400">{item.recommendation.explanation}</p>
          {signals.length > 0 && <div className="mt-2.5 flex flex-wrap gap-1.5" aria-label="Important conditions">{signals.map((signal) => <span key={signal.type} title={signal.explanation} className="rounded-full border border-white/[.08] bg-white/[.025] px-2.5 py-1 text-[10px] text-slate-400">{signal.title}</span>)}</div>}
        </div>
        <div className="flex lg:justify-end">
          {caseLinkLoading
            ? <button type="button" disabled className={`${buttonStyles.secondary} w-full whitespace-nowrap sm:w-auto`}>Connecting case...</button>
            : recoveryCase
            ? <button type="button" onClick={() => onSelectCase(recoveryCase)} className={`${buttonStyles.secondary} w-full whitespace-nowrap sm:w-auto`}>Open case</button>
            : <Link href="/analytics" className={`${buttonStyles.secondary} w-full whitespace-nowrap text-center sm:w-auto`}>Review intelligence</Link>}
        </div>
      </div>
    </article>
  );
}

function FocusLoading() {
  return (
    <div className="animate-pulse divide-y divide-white/[.055]" role="status">
      <span className="sr-only">Loading today&apos;s operational focus</span>
      {Array.from({ length: 3 }, (_, index) => <div key={index} className="grid gap-5 p-5 lg:grid-cols-[.7fr_1.5fr_auto]"><div className="h-14 rounded-xl bg-white/[.045]" /><div className="h-14 rounded-xl bg-white/[.035]" /><div className="h-9 w-24 rounded-lg bg-white/[.04]" /></div>)}
    </div>
  );
}
