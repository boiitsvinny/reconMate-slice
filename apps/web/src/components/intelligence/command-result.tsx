"use client";

import { useEffect, useMemo, useState } from "react";
import type { CommandIntentType, CommandResult, PriorityLevel } from "@/lib/intelligence-api";
import { ActionProposalCard } from "./action-proposal-card";
import { useCommandSession } from "./command-session";
import { InvestigationWorkbench } from "./investigation-workbench";
import { buttonStyles, Panel, SectionHeader, StatusPill } from "@/components/dashboard/ui";

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
  const entityNames = new Map(result.plan.entities.map((entity) => [entity.entity_id, entity.display_name]));
  const executedProposals = result.plan.proposed_actions.flatMap((proposal) => {
    const outcome = outcomes.get(proposal.proposal_id);
    return outcome?.status === "EXECUTED" ? [{ proposal, outcome }] : [];
  });
  const isUnknown = result.interpreted_intent.intent === "UNKNOWN";
  const showOperationalPlan = result.plan.execution_mode !== "READ_ONLY";
  const selectedCount = selected.size;
  const openTarget = (targetType: string, targetId: string) => {
    const opened = onOpenTarget?.(targetType, targetId) ?? false;
    setTargetNotice(opened ? null : "This result has no active recovery case workspace. Its current intelligence remains available below.");
  };
  if (isUnknown) {
    return (
      <Panel className="mt-6 border-amber-300/15">
        <SectionHeader eyebrow="Unsupported request" title="ReconMate cannot answer this from the current receivables model." detail={result.interpreted_intent.guidance ?? result.understanding_summary} prominent />
        <div className="space-y-4 p-5"><div><p className="text-[10px] font-bold uppercase tracking-[.12em] text-slate-500">Your request</p><p className="mt-1.5 text-sm leading-6 text-slate-200">“{command}”</p></div><AnalysisList title="Supported analysis dimensions" items={["Overdue exposure and invoice age", "Payments and payment activity", "Promises and broken commitments", "Disputes and action blockers", "Current risk and recovery state", "Latest operational changes"]} empty="" /></div>
      </Panel>
    );
  }

  return (
    <div className="mt-6 space-y-6" aria-live="polite">
      <section className="grid gap-4 lg:grid-cols-[minmax(0,1.08fr)_minmax(340px,.92fr)]">
        <InterpretationPanel command={command} result={result} />
        <InspectionPanel result={result} />
      </section>

      <RankedEvidencePanel result={result} onOpenTarget={onOpenTarget ? openTarget : undefined} />

      {result.query_evidence.latest_cycle && <LatestCyclePanel result={result} />}

      <InvestigationWorkbench result={result} onOpenTarget={onOpenTarget ? openTarget : undefined} />

      {executedProposals.length > 0 && (
        <Panel className="overflow-hidden border-emerald-300/20 bg-emerald-300/[.035]">
          <SectionHeader eyebrow="Confirmed outcome" title={`${executedProposals.length} internal workflow action${executedProposals.length === 1 ? "" : "s"} recorded`} detail="Confirmation created controlled RecoveryAction records from the selected proposals." prominent />
          <div className="divide-y divide-emerald-200/[.08]">
            {executedProposals.map(({ proposal, outcome }) => (
              <article key={proposal.proposal_id} className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm font-semibold text-emerald-50">{proposal.title}</p>
                  <p className="mt-1 text-xs text-emerald-100/75">Affected case: {entityNames.get(proposal.target_id) ?? proposal.target_type}</p>
                  <p className="mt-2 text-xs leading-5 text-emerald-100/75">{outcome.message}</p>
                  <p className="mt-1 text-[11px] text-emerald-100/60">{outcome.recovery_action_status ? `Workflow status: ${label(outcome.recovery_action_status)}.` : "Workflow record created."}{outcome.recovery_action_created_at ? ` Recorded ${new Date(outcome.recovery_action_created_at).toLocaleString()}.` : ""}</p>
                  {outcome.workflow_effect && <p className="mt-1 text-[11px] leading-4 text-emerald-100/60">{outcome.workflow_effect}</p>}
                </div>
                {onOpenTarget && <button type="button" onClick={() => openTarget(proposal.target_type, proposal.target_id)} className={`${buttonStyles.success} w-full sm:w-auto`}>Open affected case</button>}
              </article>
            ))}
          </div>
        </Panel>
      )}

      {showOperationalPlan && <Panel className="overflow-hidden border-sky-300/15">
        <SectionHeader eyebrow="Prepared command output" title={`Bounded work plan · ${result.plan.proposed_actions.length} proposal${result.plan.proposed_actions.length === 1 ? "" : "s"}`} detail={result.plan.proposed_actions.length > 4 ? "Ordered results are bounded inside this panel; scroll to review every proposal." : `Plan ${result.plan.plan_id.slice(0, 8)} / ${label(result.plan.execution_mode)}`} prominent action={confirmationIds.length > 0 && !reviewing ? <button type="button" onClick={() => setReviewing(true)} className={buttonStyles.warning}>Review {confirmationIds.length} action{confirmationIds.length === 1 ? "" : "s"}</button> : undefined} />
        {!result.plan.proposed_actions.length ? (
          <div className="p-10 text-center"><p className="text-sm font-medium text-slate-300">No matching action proposals</p><p className="mt-2 text-xs text-slate-500">No current record matched the interpreted command filters.</p></div>
        ) : (
          <div className="operational-scrollbar max-h-[42rem] overflow-y-auto overscroll-contain p-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-sky-300/35 lg:p-5" role="region" aria-label={`${result.plan.proposed_actions.length} operational proposals`} tabIndex={0}>
            <div className="grid gap-4 lg:grid-cols-2">
              {result.plan.proposed_actions.map((proposal) => (
                <ActionProposalCard key={proposal.proposal_id} proposal={proposal} outcome={outcomes.get(proposal.proposal_id)} targetName={entityNames.get(proposal.target_id)} selected={selected.has(proposal.proposal_id)} onSelectedChange={reviewing && proposal.requires_confirmation ? (checked) => setSelected((current) => {
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
      </Panel>}

      {(result.warnings.length > 0 || result.limitations.length > 0) && (
        <details className="rounded-2xl border border-white/[.08] bg-[#08111f]/80 p-4 sm:p-5"><summary className="cursor-pointer text-sm font-semibold text-slate-300">Notices and operating boundaries ({result.warnings.length + result.limitations.length})</summary><ul className="mt-3 space-y-2 text-xs leading-5 text-slate-500">{[...result.warnings, ...result.limitations].map((item) => <li key={item}>• {item}</li>)}</ul></details>
      )}
    </div>
  );
}

function InterpretationPanel({ command, result }: { command: string; result: CommandResult }) {
  const query = result.interpreted_intent.query;
  const conditions = queryConditions(result);
  const exclusions = queryExclusions(result);
  return <Panel className="overflow-hidden"><SectionHeader eyebrow="Query" title="What ReconMate understood" detail="The structured query produced by the command planner" prominent /><div className="space-y-4 p-5"><div><p className="text-[10px] font-bold uppercase tracking-[.12em] text-slate-500">Your request</p><p className="mt-1.5 text-sm leading-6 text-slate-200">“{command}”</p></div><div className="rounded-xl border border-sky-300/12 bg-sky-300/[.035] p-4"><p className="text-[10px] font-bold uppercase tracking-[.12em] text-sky-300">Primary objective</p><p className="mt-2 text-base font-semibold leading-6 text-white">{objectives[result.interpreted_intent.intent]}</p></div><dl className="grid gap-x-5 gap-y-3 text-xs sm:grid-cols-2"><QueryRow term="Looking for" value={query.entity === "RECOVERY_CASES" ? "Recovery cases" : "Customers"} /><QueryRow term="Conditions" value={conditions.join(" + ") || "Current portfolio state"} /><QueryRow term="Excluded" value={exclusions.join(" + ") || "No explicit exclusions"} /><QueryRow term="Order" value={queryOrder(result)} /><QueryRow term="Limit" value={query.count_only ? "Count only" : query.limit ? String(query.limit) : "All matches"} /><QueryRow term="Scope" value={query.time_scope === "LATEST_CYCLE" ? "Latest simulation cycle" : "Current portfolio"} /></dl></div></Panel>;
}

function InspectionPanel({ result }: { result: CommandResult }) {
  const evidence = result.query_evidence;
  const scope = evidence.inspection_scope;
  const scopeItems = [[scope.customers, "customers"], [scope.invoices, "invoices"], [scope.promises, "promises"], [scope.active_disputes, "active disputes"], [scope.recovery_cases, "recovery cases"], [scope.latest_cycle_events, "latest-cycle events"]] as const;
  return <Panel className="overflow-hidden"><SectionHeader eyebrow="Grounded execution" title="What ReconMate inspected" detail={result.interpreted_intent.reasoning[0]} prominent /><div className="space-y-4 p-5"><div className="grid grid-cols-2 gap-3"><Metric label="Records inspected" value={String(evidence.records_inspected)} /><Metric label="Matched" value={String(evidence.records_matched)} /><Metric label="Excluded" value={String(evidence.records_excluded)} /><Metric label={result.interpreted_intent.query.count_only ? "Count result" : "Returned"} value={String(result.interpreted_intent.query.count_only ? evidence.records_matched : evidence.records_returned)} /></div><AnalysisList title="Operational scope considered" items={scopeItems.filter(([count]) => count > 0).map(([count, name]) => `${count} ${name}`)} empty="No operational records were available to inspect." /><AnalysisList title="Filtered from the inspected set" items={evidence.exclusions.map((item) => `${item.count} excluded: ${item.reason}`)} empty="No records were excluded by the applied conditions." /></div></Panel>;
}

function LatestCyclePanel({ result }: { result: CommandResult }) {
  const cycle = result.query_evidence.latest_cycle!;
  return <Panel className="overflow-hidden border-cyan-300/15"><SectionHeader eyebrow="Scoped latest-cycle evidence" title="What changed for these returned records" detail={`Cycle ${cycle.cycle} · ${cycle.event_count} provably associated event${cycle.event_count === 1 ? "" : "s"} across ${cycle.customers_affected} returned customer${cycle.customers_affected === 1 ? "" : "s"}`} prominent /><div className="grid gap-4 p-5 lg:grid-cols-[minmax(0,.72fr)_minmax(0,1.28fr)]"><div className="grid grid-cols-2 gap-3"><Metric label="Material changes" value={String(cycle.material_customers)} /><Metric label="Decisions changed" value={String(cycle.recommendations_changed)} /><Metric label="Decisions held" value={String(cycle.recommendations_unchanged)} /><Metric label="Events associated" value={String(cycle.event_count)} /></div><AnalysisList title="Factual before/after observations" items={cycle.observations} empty="Associated events were found without a material decision transition." /></div></Panel>;
}

function RankedEvidencePanel({ result, onOpenTarget }: { result: CommandResult; onOpenTarget?: (targetType: string, targetId: string) => void }) {
  const evidence = result.query_evidence;
  const names = new Map(result.analyzed_entities.map((entity) => [entity.entity_id, entity.entity_name]));
  if (!evidence.ranking.length) return <Panel className="overflow-hidden"><SectionHeader eyebrow="Query outcome" title={evidence.records_matched === 0 ? "No records matched the structured query" : `${evidence.records_matched} matching record${evidence.records_matched === 1 ? "" : "s"} counted`} detail={evidence.records_matched === 0 ? `ReconMate inspected ${evidence.records_inspected} records and applied every condition shown above.` : "This count comes from current operational records; no ranked rows were requested."} prominent /></Panel>;
  return <Panel className="overflow-hidden"><SectionHeader eyebrow="What matched" title="Returned records and ranking evidence" detail={`${evidence.records_returned} of ${evidence.records_matched} matching record${evidence.records_matched === 1 ? "" : "s"} returned in the structured query order`} prominent /><div className="divide-y divide-white/[.06]">{evidence.ranking.map((item) => <article key={item.entity_id} className="interactive-row p-5 sm:p-6"><div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><p className="text-[11px] font-bold uppercase tracking-[.12em] text-sky-300">Rank #{item.rank}</p><h3 className="mt-1 text-lg font-semibold text-white">{names.get(item.entity_id) ?? item.entity_id}</h3></div><div className="flex flex-wrap items-center gap-2"><StatusPill tone={tone(item.severity)}>{item.severity} risk</StatusPill><span className="text-[13px] font-medium text-slate-300">Current Intelligence Score {item.score}/100{item.raw_score !== item.score ? ` · raw ${item.raw_score}` : ""}</span></div></div><div className="mt-5 grid gap-5 lg:grid-cols-3"><AnalysisList title="Why it matched" items={item.facts} empty="No material factual factor was recorded." /><AnalysisList title="Actionability and workflow state" items={[...(item.blocker ? [item.blocker] : ["No current action blocker detected"]), ...(item.stored_workflow_priority ? [`Stored workflow priority: ${label(item.stored_workflow_priority)}`] : [])]} empty="" /><div><p className="text-[11px] font-bold uppercase tracking-[.12em] text-slate-400">Current recommended action</p><p className="mt-2 text-[13px] font-medium leading-6 text-slate-200">{item.decision}</p>{onOpenTarget && <button type="button" onClick={() => onOpenTarget(result.interpreted_intent.query.entity === "RECOVERY_CASES" ? "RECOVERY_CASE" : "CUSTOMER", item.entity_id)} className="mt-3 text-xs font-semibold text-sky-300 hover:text-sky-200">Open supporting record →</button>}</div></div></article>)}</div></Panel>;
}

function QueryRow({ term, value }: { term: string; value: string }) {
  return <div><dt className="text-[11px] font-bold uppercase tracking-[.12em] text-slate-400">{term}</dt><dd className="mt-1 text-[13px] leading-5 text-slate-200">{value}</dd></div>;
}

function AnalysisList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return <div><p className="text-[11px] font-bold uppercase tracking-[.12em] text-slate-400">{title}</p>{items.length ? <ul className="mt-2 space-y-1.5 text-[13px] leading-5 text-slate-200">{items.map((item) => <li key={item} className="flex gap-2"><span className="text-sky-300">•</span><span>{item}</span></li>)}</ul> : <p className="mt-2 text-xs leading-5 text-slate-500">{empty}</p>}</div>;
}

function queryConditions(result: CommandResult): string[] {
  const query = result.interpreted_intent.query;
  const booleans = [[query.overdue, "Overdue"], [query.broken_promise, "Broken promise"], [query.active_promise, "Active promise"], [query.active_dispute, "Active dispute"], [query.partial_payment, "Partial payment"], [query.recent_payment, "Recent payment"], [query.actionable, "Actionable"], [query.blocked, "Blocked"], [query.monitoring, "Monitoring"]] as const;
  return [...query.risk_levels.map((level) => `${label(level)} risk`), ...booleans.filter(([value]) => value === true).map(([, text]) => text), ...(query.min_days_overdue !== null ? [`At least ${query.min_days_overdue} days overdue`] : []), ...(query.max_days_overdue !== null ? [`At most ${query.max_days_overdue} days overdue`] : []), ...(query.min_score !== null ? [`Score at least ${query.min_score}`] : []), ...(query.max_score !== null ? [`Score at most ${query.max_score}`] : [])];
}

function queryExclusions(result: CommandResult): string[] {
  const query = result.interpreted_intent.query;
  const booleans = [[query.overdue, "No overdue exposure"], [query.broken_promise, "Broken promises"], [query.active_promise, "Active promises"], [query.active_dispute, "Active disputes"], [query.partial_payment, "Partial payments"], [query.recent_payment, "Recent payments"], [query.actionable, "Actionable records"], [query.blocked, "Blocked records"], [query.monitoring, "Monitoring records"]] as const;
  return booleans.filter(([value]) => value === false).map(([, text]) => text);
}

function queryOrder(result: CommandResult): string {
  const query = result.interpreted_intent.query;
  const names = { RISK_SCORE: "current intelligence score", TOTAL_EXPOSURE: "total exposure", OVERDUE_EXPOSURE: "overdue exposure", DAYS_OVERDUE: "oldest invoice age", LAST_PAYMENT: "latest payment activity" };
  return `${query.descending ? "Highest" : "Lowest"} ${names[query.sort_by]}`;
}

function Metric({ label: metricLabel, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-white/[.07] bg-white/[.025] p-3"><p className="text-[10px] uppercase tracking-[.12em] text-slate-600">{metricLabel}</p><p className="mt-2 text-base font-semibold text-white">{value}</p></div>;
}
