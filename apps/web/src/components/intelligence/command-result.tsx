"use client";

import { useEffect, useMemo, useState } from "react";
import type { CommandIntentType, CommandResult, ContributingFactor, IntelligenceSignal, PriorityLevel } from "@/lib/intelligence-api";
import { ActionProposalCard } from "./action-proposal-card";
import { useCommandSession } from "./command-session";
import { buttonStyles, cx, Panel, SectionHeader, StatusPill } from "@/components/dashboard/ui";

const label = (value: string) => value.replaceAll("_", " ");
const tone = (level: PriorityLevel) => level === "CRITICAL" ? "rose" : level === "HIGH" ? "amber" : level === "MEDIUM" ? "sky" : "slate";

const objectives: Record<CommandIntentType, string> = {
  PORTFOLIO_ANALYSIS: "Assess current portfolio health and surface the highest-priority accounts",
  CUSTOMER_ANALYSIS: "Explain the selected customer's current recovery position",
  CASE_ANALYSIS: "Analyze the selected recovery case from current factual records",
  PRIORITIZE_CASES: "Rank the customers that require operator attention",
  PREPARE_FOLLOW_UPS: "Prepare follow-up work for recovery cases linked to broken promises",
  PREPARE_RECOVERY_ACTIONS: "Prepare controlled recovery work for matching cases",
  PREPARE_PAYMENT_REMINDERS: "Prepare payment-reminder drafts for customers with overdue receivables",
  EXPLAIN_RECOMMENDATION: "Explain why the selected case has its current recommendation",
  REVIEW_BROKEN_PROMISES: "Identify customers with factually broken payment promises",
  UNKNOWN: "Map the request to a supported operational objective",
};

export function CommandResultView({ command, result, onOpenTarget }: { command: string; result: CommandResult; onOpenTarget?: (targetType: string, targetId: string) => boolean }) {
  const { confirmPlan, confirming } = useCommandSession();
  const confirmationIds = useMemo(() => result.outcomes.filter((item) => item.status === "AWAITING_CONFIRMATION").map((item) => item.proposal_id), [result.outcomes]);
  const [selected, setSelected] = useState<Set<string>>(new Set(confirmationIds));
  const [reviewing, setReviewing] = useState(false);
  const [targetNotice, setTargetNotice] = useState<string | null>(null);

  useEffect(() => {
    setSelected(new Set(confirmationIds));
    setReviewing(false);
    setTargetNotice(null);
  }, [result.plan_id, confirmationIds]);

  const outcomes = new Map(result.outcomes.map((item) => [item.proposal_id, item]));
  const isUnknown = result.interpreted_intent.intent === "UNKNOWN";
  const selectedCount = selected.size;
  const executedCount = result.outcomes.filter((item) => item.status === "EXECUTED").length;
  const awaitingCount = result.outcomes.filter((item) => item.status === "AWAITING_CONFIRMATION").length;
  const preparedCount = result.outcomes.filter((item) => item.status === "PREPARED").length;

  if (isUnknown) {
    return (
      <Panel className="mt-6 border-amber-300/15">
        <SectionHeader eyebrow="Command not mapped" title="ReconMate needs a supported operational request" detail={result.interpreted_intent.guidance ?? result.understanding_summary} prominent />
        <p className="p-5 text-sm leading-6 text-slate-300">Try a portfolio prioritization, broken-promise review, recovery preparation, or reminder-drafting command.</p>
      </Panel>
    );
  }

  return (
    <div className="mt-6 space-y-6" aria-live="polite">
      <CommandFlow />
      <div className={cx("rounded-2xl border p-4 sm:p-5", executedCount ? "border-emerald-300/20 bg-emerald-300/[.06]" : awaitingCount ? "border-amber-300/20 bg-amber-300/[.06]" : "border-sky-300/20 bg-sky-300/[.055]")} role="status">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <div>
            <p className={cx("text-sm font-semibold", executedCount ? "text-emerald-100" : awaitingCount ? "text-amber-100" : "text-sky-100")}>
              {executedCount ? `${executedCount} workflow action${executedCount === 1 ? "" : "s"} created` : awaitingCount ? "Plan ready for operator review" : preparedCount ? "Preparation complete" : "Analysis complete"}
            </p>
            <p className="mt-1 text-xs leading-5 text-slate-300/75">
              {executedCount ? "The confirmed internal workflow work is now reflected in current recovery data." : awaitingCount ? "Review the proposed actions below and explicitly confirm only the work you want created." : preparedCount ? "The requested drafts are ready for review. Nothing was sent to a customer." : "The command inspected current operational data and completed without changing portfolio records."}
            </p>
          </div>
          <StatusPill tone={executedCount ? "emerald" : awaitingCount ? "amber" : "sky"}>{label(result.plan.execution_mode)}</StatusPill>
        </div>
      </div>

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1.08fr)_minmax(340px,.92fr)]">
        <InterpretationPanel command={command} result={result} />
        <AnalysisApproach result={result} />
      </section>

      <Panel className="overflow-hidden border-sky-300/15">
        <SectionHeader eyebrow="Prioritized operational plan" title={`Action plan · ${result.plan.proposed_actions.length} proposal${result.plan.proposed_actions.length === 1 ? "" : "s"}`} detail={result.plan.proposed_actions.length > 4 ? "Ordered results are bounded inside this panel; scroll to review every proposal." : `Plan ${result.plan.plan_id.slice(0, 8)} / ${label(result.plan.execution_mode)}`} prominent action={confirmationIds.length > 0 && !reviewing ? <button type="button" onClick={() => setReviewing(true)} className={buttonStyles.warning}>Review {confirmationIds.length} action{confirmationIds.length === 1 ? "" : "s"}</button> : undefined} />
        {!result.plan.proposed_actions.length ? (
          <div className="p-10 text-center"><p className="text-sm font-medium text-slate-300">No matching action proposals</p><p className="mt-2 text-xs text-slate-500">No current record matched the interpreted command filters.</p></div>
        ) : (
          <div className="operational-scrollbar max-h-[42rem] overflow-y-auto overscroll-contain p-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-sky-300/35 lg:p-5" role="region" aria-label={`${result.plan.proposed_actions.length} operational proposals`} tabIndex={0}>
            <div className="grid gap-4 lg:grid-cols-2">
              {result.plan.proposed_actions.map((proposal) => (
                <ActionProposalCard key={proposal.proposal_id} proposal={proposal} outcome={outcomes.get(proposal.proposal_id)} selected={selected.has(proposal.proposal_id)} onSelectedChange={reviewing && proposal.requires_confirmation ? (checked) => setSelected((current) => {
                  const next = new Set(current);
                  if (checked) next.add(proposal.proposal_id); else next.delete(proposal.proposal_id);
                  return next;
                }) : undefined} onOpenTarget={onOpenTarget && (proposal.target_type === "CUSTOMER" || proposal.target_type === "RECOVERY_CASE" || proposal.target_type === "CASE") ? () => {
                  const opened = onOpenTarget(proposal.target_type, proposal.target_id);
                  setTargetNotice(opened ? null : "This result has no active recovery case workspace. Its current intelligence remains available below.");
                } : undefined} />
              ))}
            </div>
          </div>
        )}
        {targetNotice && <p className="border-t border-amber-300/15 bg-amber-300/[.04] px-5 py-3 text-xs text-amber-100" role="status">{targetNotice}</p>}
        {reviewing && confirmationIds.length > 0 && (
          <div className="border-t border-amber-300/15 bg-amber-300/[.035] p-4 sm:p-5">
            <h3 className="text-lg font-semibold text-amber-50">Confirm selected internal workflow actions</h3>
            <p className="mt-2 max-w-3xl text-xs leading-5 text-amber-100/70">Confirmation creates internal recovery workflow records only. It does not contact customers or change financial facts. This plan is single-use and expires after 30 minutes.</p>
            <div className="mt-4 flex flex-col gap-2 sm:flex-row"><button type="button" onClick={() => setReviewing(false)} className={`${buttonStyles.secondary} w-full sm:w-auto`}>Cancel review</button><button type="button" disabled={!selectedCount || confirming} onClick={() => void confirmPlan([...selected])} className={`${buttonStyles.warning} w-full sm:w-auto`}>{confirming ? "Confirming safely..." : `Confirm ${selectedCount} selected action${selectedCount === 1 ? "" : "s"}`}</button></div>
          </div>
        )}
      </Panel>

      <Panel className="overflow-hidden">
        <SectionHeader eyebrow="Recommendation evidence" title="Why ReconMate recommends this" detail={`${result.analyzed_entities.length} detailed intelligence record${result.analyzed_entities.length === 1 ? "" : "s"} returned by the command`} prominent />
        <div className="operational-scrollbar max-h-[34rem] divide-y divide-white/[.06] overflow-y-auto overscroll-contain" role="region" aria-label="Recommendation evidence" tabIndex={0}>
          {result.analyzed_entities.map((entity) => (
            <details key={`${entity.entity_type}-${entity.entity_id}`} className="group p-4 sm:p-5" open={result.analyzed_entities.length === 1}>
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300/40"><div><p className="text-sm font-semibold text-white">{entity.entity_name}</p><p className="mt-1 text-xs text-slate-500">Score {entity.score}/100 / {entity.recommendation.title}</p></div><StatusPill tone={tone(entity.level)}>{entity.level}</StatusPill></summary>
              <div className="mt-4 grid gap-3 md:grid-cols-2">{(entity.factors.length ? entity.factors : entity.signals).map((factor) => <FactorExplanation key={`${factor.type}-${factor.explanation}`} factor={factor} />)}{!entity.factors.length && !entity.signals.length && <p className="text-xs text-slate-500">No material intelligence factor is currently detected.</p>}</div>
            </details>
          ))}
          {!result.analyzed_entities.length && <p className="p-8 text-center text-xs text-slate-500">No intelligence records matched this command.</p>}
        </div>
      </Panel>

      {(result.warnings.length > 0 || result.limitations.length > 0) && (
        <details className="rounded-2xl border border-white/[.08] bg-[#08111f]/80 p-4 sm:p-5"><summary className="cursor-pointer text-sm font-semibold text-slate-300">Notices and operating boundaries ({result.warnings.length + result.limitations.length})</summary><ul className="mt-3 space-y-2 text-xs leading-5 text-slate-500">{[...result.warnings, ...result.limitations].map((item) => <li key={item}>• {item}</li>)}</ul></details>
      )}
    </div>
  );
}

function CommandFlow() {
  return <ol className="grid overflow-hidden rounded-2xl border border-white/[.08] bg-[#08111f]/80 sm:grid-cols-5" aria-label="Command analysis flow">{["Request received", "Intent understood", "Live records inspected", "Plan prioritized", "Operator reviews"].map((step, index) => <li key={step} className="flex items-center gap-3 border-b border-white/[.06] px-3 py-3 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0"><span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-sky-300 text-[10px] font-bold text-slate-950">{index + 1}</span><span className="text-[11px] font-semibold text-slate-300">{step}</span></li>)}</ol>;
}

function InterpretationPanel({ command, result }: { command: string; result: CommandResult }) {
  return <Panel className="overflow-hidden"><SectionHeader eyebrow="Request interpretation" title="What ReconMate understood" detail="The structured objective returned by the command pipeline" prominent /><div className="space-y-4 p-5"><div><p className="text-[10px] font-bold uppercase tracking-[.12em] text-slate-500">Your request</p><p className="mt-1.5 text-sm leading-6 text-slate-200">“{command}”</p></div><div className="rounded-xl border border-sky-300/12 bg-sky-300/[.035] p-4"><p className="text-[10px] font-bold uppercase tracking-[.12em] text-sky-300">Primary objective</p><p className="mt-2 text-base font-semibold leading-6 text-white">{objectives[result.interpreted_intent.intent]}</p></div><p className="text-xs leading-5 text-slate-400">{result.understanding_summary}</p><div className="grid grid-cols-2 gap-3"><Metric label="Target records" value={targetLabel(result.interpreted_intent.intent)} /><Metric label="Detailed records" value={String(result.analyzed_entities.length)} /></div></div></Panel>;
}

function AnalysisApproach({ result }: { result: CommandResult }) {
  const filters = filterLabels(result);
  const conditions = detectedConditions(result);
  const factors = [...new Set(result.analyzed_entities.flatMap((entity) => entity.factors.map((factor) => label(factor.type))))];
  return <Panel className="overflow-hidden"><SectionHeader eyebrow="Analysis approach" title="What ReconMate inspected" detail={result.interpreted_intent.reasoning[0]} prominent /><div className="space-y-4 p-5"><p className="text-xs leading-5 text-slate-400">{analysisNarrative(result.interpreted_intent.intent)}</p><AnalysisList title="Explicit command filters" items={filters} empty="No additional filter was explicitly selected." /><AnalysisList title="Conditions found in returned records" items={conditions} empty="No material condition was found in the returned records." /><AnalysisList title="Intelligence factors considered" items={factors} empty="No scored intelligence factor was present in the returned records." /></div></Panel>;
}

function AnalysisList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return <div><p className="text-[10px] font-bold uppercase tracking-[.12em] text-slate-500">{title}</p>{items.length ? <ul className="mt-2 space-y-1.5 text-xs leading-5 text-slate-300">{items.map((item) => <li key={item} className="flex gap-2"><span className="text-sky-300">•</span><span>{item}</span></li>)}</ul> : <p className="mt-2 text-xs leading-5 text-slate-500">{empty}</p>}</div>;
}

function FactorExplanation({ factor }: { factor: ContributingFactor | IntelligenceSignal }) {
  const scored = "points" in factor;
  const impact = scored ? factor.impact : factor.severity;
  return <article className="rounded-xl border border-white/[.07] bg-white/[.02] p-4"><div className="flex items-center justify-between gap-3"><p className="text-xs font-semibold text-sky-200">{scored ? label(factor.type) : factor.title}</p><StatusPill tone={tone(impact)}>{impact}</StatusPill></div><p className="mt-3 text-xs leading-5 text-slate-300"><span className="font-semibold text-slate-200">What happened:</span> {factor.explanation}</p><p className="mt-2 text-[11px] leading-5 text-slate-500"><span className="font-semibold text-slate-400">Why it matters:</span> The current intelligence rules classify this as {impact.toLowerCase()} operational impact.</p><p className="mt-2 text-[11px] leading-5 text-slate-500"><span className="font-semibold text-slate-400">Influence:</span> {scored ? `Contributed ${factor.points} points to the current priority score.` : "Contributed a factual signal to the recommendation evaluation."}</p></article>;
}

function filterLabels(result: CommandResult): string[] {
  const filters = result.interpreted_intent.filters;
  return [...filters.risk_levels.map((level) => `${label(level)} risk`), ...(filters.top_n ? [`Top ${filters.top_n} matching records`] : []), ...(filters.overdue_only ? ["Overdue receivables only"] : []), ...(filters.broken_promises_only ? ["Customers with broken promises"] : []), ...(filters.include_all ? ["All matching records"] : [])];
}

function detectedConditions(result: CommandResult): string[] {
  const entities = result.analyzed_entities;
  const count = (test: (entity: CommandResult["analyzed_entities"][number]) => boolean) => entities.filter(test).length;
  const conditions = [[count((item) => Number(item.metrics.overdue_exposure) > 0), "with overdue exposure"], [count((item) => item.metrics.broken_promise_count > 0), "with broken payment promises"], [count((item) => item.metrics.active_promise_count > 0), "with active payment promises"], [count((item) => item.metrics.active_dispute_count > 0), "with active disputes"], [count((item) => item.metrics.stalled_recovery_case_count > 0), "with stalled recovery work"]] as const;
  return conditions.filter(([value]) => value > 0).map(([value, text]) => `${value} returned record${value === 1 ? "" : "s"} ${text}`);
}

function targetLabel(intent: CommandIntentType) {
  if (intent === "CASE_ANALYSIS" || intent === "EXPLAIN_RECOMMENDATION" || intent === "PREPARE_FOLLOW_UPS" || intent === "PREPARE_RECOVERY_ACTIONS") return "Recovery cases";
  if (intent === "PORTFOLIO_ANALYSIS") return "Portfolio + priority accounts";
  return "Customer accounts";
}

function analysisNarrative(intent: CommandIntentType) {
  if (intent === "PREPARE_PAYMENT_REMINDERS") return "ReconMate reviewed current overdue customer records and their payment, promise, dispute, and recovery conditions before preparing reminder drafts.";
  if (intent === "PREPARE_RECOVERY_ACTIONS" || intent === "PREPARE_FOLLOW_UPS") return "ReconMate reviewed matching recovery cases, applied current intelligence priority, and respected factual blockers before preparing controlled workflow proposals.";
  if (intent === "REVIEW_BROKEN_PROMISES") return "ReconMate selected customers carrying a current broken-promise signal and evaluated their live operational intelligence.";
  if (intent === "CASE_ANALYSIS" || intent === "EXPLAIN_RECOMMENDATION") return "ReconMate inspected the selected case, its customer, invoice, payments, promises, communications, and recorded recovery work.";
  if (intent === "CUSTOMER_ANALYSIS") return "ReconMate inspected the selected customer's invoices, payments, promises, disputes, and recovery cases.";
  return "ReconMate evaluated current portfolio intelligence and returned the records that best match the interpreted objective and filters.";
}

function Metric({ label: metricLabel, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-white/[.07] bg-white/[.025] p-3"><p className="text-[10px] uppercase tracking-[.12em] text-slate-600">{metricLabel}</p><p className="mt-2 text-base font-semibold text-white">{value}</p></div>;
}
