"use client";

import { useEffect, useMemo, useState } from "react";
import type { CommandResult, PriorityLevel } from "@/lib/intelligence-api";
import { ActionProposalCard } from "./action-proposal-card";
import { useCommandSession } from "./command-session";
import { buttonStyles, cx, Panel, SectionHeader, StatusPill } from "@/components/dashboard/ui";

const label = (value: string) => value.replaceAll("_", " ");
const tone = (level: PriorityLevel) => level === "CRITICAL" ? "rose" : level === "HIGH" ? "amber" : level === "MEDIUM" ? "sky" : "slate";

export function CommandResultView({
  result,
  onOpenTarget,
}: {
  result: CommandResult;
  onOpenTarget?: (targetType: string, targetId: string) => boolean;
}) {
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
        <SectionHeader eyebrow="Command not mapped" title="ReconMate needs a supported operational request" detail={result.interpreted_intent.guidance ?? result.understanding_summary} />
        <div className="p-5 text-sm text-slate-300">
          <p>Try one of these:</p>
          <ul className="mt-3 space-y-2 text-xs text-slate-400">
            <li>Who should I focus on today?</li>
            <li>Show me customers with broken promises</li>
            <li>Prepare recovery actions for critical cases</li>
            <li>Draft payment reminders for overdue customers</li>
          </ul>
        </div>
      </Panel>
    );
  }

  return (
    <div className="mt-6 space-y-6" aria-live="polite">
      <div className={cx(
        "rounded-2xl border p-4 sm:p-5",
        executedCount ? "border-emerald-300/20 bg-emerald-300/[.06]" : awaitingCount ? "border-amber-300/20 bg-amber-300/[.06]" : "border-sky-300/20 bg-sky-300/[.055]",
      )} role="status">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <div>
            <p className={cx("text-sm font-semibold", executedCount ? "text-emerald-100" : awaitingCount ? "text-amber-100" : "text-sky-100")}>
              {executedCount ? `${executedCount} workflow action${executedCount === 1 ? "" : "s"} created` : awaitingCount ? "Plan ready for your review" : preparedCount ? "Preparation complete" : "Analysis complete"}
            </p>
            <p className="mt-1 text-xs leading-5 text-slate-300/75">
              {executedCount
                ? "The dashboard data has been refreshed with the confirmed internal workflow work."
                : awaitingCount
                  ? "Nothing has been changed yet. Review the proposed actions below, select what you want, and confirm explicitly."
                  : preparedCount
                    ? "The requested drafts are shown below. Nothing was sent and no customer was contacted."
                    : "ReconMate analyzed current data. This was a read-only command, so no portfolio records were changed."}
            </p>
          </div>
          <StatusPill tone={executedCount ? "emerald" : awaitingCount ? "amber" : "sky"}>{label(result.plan.execution_mode)}</StatusPill>
        </div>
      </div>
      <section className="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(300px,.9fr)]">
        <Panel>
          <SectionHeader eyebrow="Understood" title={label(result.interpreted_intent.intent)} detail={result.understanding_summary} />
          <div className="grid gap-4 p-5 sm:grid-cols-3">
            <Metric label="Confidence" value={`${Math.round(result.interpreted_intent.confidence * 100)}%`} />
            <Metric label="Scope" value={label(result.interpreted_intent.scope)} />
            <Metric label="Records analyzed" value={String(result.analyzed_entities.length)} />
          </div>
        </Panel>
        <Panel>
          <SectionHeader eyebrow="Analysis" title="Applied portfolio scope" detail="Filters interpreted by the backend command layer" />
          <div className="flex flex-wrap gap-2 p-5">
            {result.interpreted_intent.filters.risk_levels.map((level) => <StatusPill key={level} tone={tone(level)}>{level}</StatusPill>)}
            {result.interpreted_intent.filters.top_n && <StatusPill tone="sky">Top {result.interpreted_intent.filters.top_n}</StatusPill>}
            {result.interpreted_intent.filters.overdue_only && <StatusPill tone="amber">Overdue only</StatusPill>}
            {result.interpreted_intent.filters.broken_promises_only && <StatusPill tone="rose">Broken promises</StatusPill>}
            {result.interpreted_intent.filters.include_all && <StatusPill tone="slate">All matching</StatusPill>}
            {!result.interpreted_intent.filters.risk_levels.length && !result.interpreted_intent.filters.top_n && !result.interpreted_intent.filters.overdue_only && !result.interpreted_intent.filters.broken_promises_only && !result.interpreted_intent.filters.include_all && <span className="text-xs text-slate-500">No additional scope filters were required.</span>}
          </div>
        </Panel>
      </section>

      <Panel>
        <SectionHeader
          eyebrow="Action plan"
          title={`${result.plan.proposed_actions.length} operational proposal${result.plan.proposed_actions.length === 1 ? "" : "s"}`}
          detail={`Plan ${result.plan.plan_id.slice(0, 8)} / ${label(result.plan.execution_mode)}`}
          action={confirmationIds.length > 0 && !reviewing ? <button type="button" onClick={() => setReviewing(true)} className={buttonStyles.warning}>Review {confirmationIds.length} action{confirmationIds.length === 1 ? "" : "s"}</button> : undefined}
        />
        {!result.plan.proposed_actions.length ? (
          <div className="p-10 text-center"><p className="text-sm font-medium text-slate-300">No matching action proposals</p><p className="mt-2 text-xs text-slate-500">ReconMate found no current records matching this command and did not invent work.</p></div>
        ) : (
          <div className="grid gap-4 p-4 lg:grid-cols-2 lg:p-5">
            {result.plan.proposed_actions.map((proposal) => (
              <ActionProposalCard
                key={proposal.proposal_id}
                proposal={proposal}
                outcome={outcomes.get(proposal.proposal_id)}
                selected={selected.has(proposal.proposal_id)}
                onSelectedChange={reviewing && proposal.requires_confirmation ? (checked) => setSelected((current) => {
                  const next = new Set(current);
                  if (checked) next.add(proposal.proposal_id); else next.delete(proposal.proposal_id);
                  return next;
                }) : undefined}
                onOpenTarget={onOpenTarget && (proposal.target_type === "CUSTOMER" || proposal.target_type === "RECOVERY_CASE" || proposal.target_type === "CASE")
                  ? () => {
                    const opened = onOpenTarget(proposal.target_type, proposal.target_id);
                    setTargetNotice(opened ? null : "This record has no active recovery case workspace. Its live analysis is shown below.");
                  }
                  : undefined}
              />
            ))}
          </div>
        )}
        {targetNotice && <p className="border-t border-amber-300/15 bg-amber-300/[.04] px-5 py-3 text-xs text-amber-100" role="status">{targetNotice}</p>}
        {reviewing && confirmationIds.length > 0 && (
          <div className="border-t border-amber-300/15 bg-amber-300/[.035] p-4 sm:p-5">
            <h3 className="text-sm font-semibold text-amber-50">Confirm selected internal workflow actions</h3>
            <p className="mt-2 max-w-3xl text-xs leading-5 text-amber-100/70">This creates internal, approval-controlled recovery workflow records only. It will not contact customers, send messages, dispatch payment links, or change financial facts. The plan is single-use and may expire after 30 minutes.</p>
            <div className="mt-4 flex flex-col gap-2 sm:flex-row">
              <button type="button" onClick={() => setReviewing(false)} className={`${buttonStyles.secondary} w-full sm:w-auto`}>Cancel review</button>
              <button type="button" disabled={!selectedCount || confirming} onClick={() => void confirmPlan([...selected])} className={`${buttonStyles.warning} w-full sm:w-auto`}>{confirming ? "Confirming safely..." : `Confirm ${selectedCount} selected action${selectedCount === 1 ? "" : "s"}`}</button>
            </div>
          </div>
        )}
      </Panel>

      <Panel>
        <SectionHeader eyebrow="Why this matters" title="Intelligence factors behind the plan" detail="Current backend signals and explanations—not generated frontend reasoning" />
        <div className="divide-y divide-white/[.06]">
          {result.analyzed_entities.slice(0, 8).map((entity) => (
            <details key={`${entity.entity_type}-${entity.entity_id}`} className="group p-4 sm:p-5">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4">
                <div><p className="text-sm font-semibold text-white">{entity.entity_name}</p><p className="mt-1 text-xs text-slate-500">Score {entity.score}/100 / {entity.recommendation.title}</p></div>
                <StatusPill tone={tone(entity.level)}>{entity.level}</StatusPill>
              </summary>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                {(entity.factors.length ? entity.factors : entity.signals).map((factor) => (
                  <div key={`${factor.type}-${factor.explanation}`} className="rounded-xl border border-white/[.07] bg-white/[.02] p-3">
                    <p className="text-[10px] font-bold uppercase tracking-[.1em] text-sky-300">{label(factor.type)}</p>
                    <p className="mt-2 text-xs leading-5 text-slate-400">{factor.explanation}</p>
                  </div>
                ))}
                {!entity.factors.length && !entity.signals.length && <p className="text-xs text-slate-500">No material risk factor is currently detected.</p>}
              </div>
            </details>
          ))}
          {!result.analyzed_entities.length && <p className="p-8 text-center text-xs text-slate-500">No intelligence records matched this command.</p>}
        </div>
      </Panel>

      {(result.warnings.length > 0 || result.limitations.length > 0) && (
        <Panel className="p-4 sm:p-5">
          <p className="text-[10px] font-bold uppercase tracking-[.15em] text-slate-500">Boundaries and notices</p>
          <ul className="mt-3 space-y-2 text-xs leading-5 text-slate-400">
            {[...result.warnings, ...result.limitations].map((item) => <li key={item}>• {item}</li>)}
          </ul>
        </Panel>
      )}
    </div>
  );
}

function Metric({ label: metricLabel, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-white/[.07] bg-white/[.025] p-3"><p className="text-[10px] uppercase tracking-[.12em] text-slate-600">{metricLabel}</p><p className="mt-2 text-lg font-semibold text-white">{value}</p></div>;
}
