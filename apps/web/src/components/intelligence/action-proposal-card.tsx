"use client";

import type { ActionOutcome, ActionProposal, PriorityLevel } from "@/lib/intelligence-api";
import { buttonStyles, cx, StatusPill } from "@/components/dashboard/ui";

const label = (value: string) => value.replaceAll("_", " ");
const tone = (level: PriorityLevel) => level === "CRITICAL" ? "rose" : level === "HIGH" ? "amber" : level === "MEDIUM" ? "sky" : "slate";
const statusTone = (status: ActionOutcome["status"]) => status === "EXECUTED" ? "emerald" : status === "FAILED" || status === "NOT_EXECUTABLE" ? "rose" : status === "AWAITING_CONFIRMATION" ? "amber" : "sky";
const outcomeLabel = (proposal: ActionProposal, outcome?: ActionOutcome) => {
  if (outcome?.status === "EXECUTED") return "Internal action recorded";
  if (outcome?.status === "AWAITING_CONFIRMATION") return "Decision required";
  if (outcome?.status === "PREPARED") return "Prepared for review";
  if (outcome?.status === "ANALYZED") return "Analysis only";
  if (outcome?.status === "NOT_EXECUTABLE") return "Safeguard active";
  if (outcome?.status === "FAILED") return "Action not recorded";
  return proposal.execution_mode === "READ_ONLY" ? "Analysis only" : "Prepared for review";
};

export function ActionProposalCard({
  proposal,
  outcome,
  selected,
  onSelectedChange,
  onOpenTarget,
  targetName,
}: {
  proposal: ActionProposal;
  outcome?: ActionOutcome;
  selected?: boolean;
  onSelectedChange?: (selected: boolean) => void;
  onOpenTarget?: () => void;
  targetName?: string;
}) {
  const openTarget = () => onOpenTarget?.();

  return (
    <article
      className={cx(
      "rounded-2xl border p-4 transition sm:p-5",
      onOpenTarget && "cursor-pointer hover:border-sky-300/35 hover:bg-sky-300/[.045] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300/45 active:scale-[.99]",
      proposal.risk_level === "CRITICAL" ? "border-rose-300/20 bg-rose-300/[.035]" : "border-white/[.08] bg-white/[.025]",
      )}
      role={onOpenTarget ? "button" : undefined}
      tabIndex={onOpenTarget ? 0 : undefined}
      onClick={openTarget}
      onKeyDown={onOpenTarget ? (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openTarget();
        }
      } : undefined}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill tone={tone(proposal.priority)}>{proposal.priority} priority</StatusPill>
            <StatusPill tone={statusTone(outcome?.status ?? (proposal.requires_confirmation ? "AWAITING_CONFIRMATION" : proposal.execution_mode === "READ_ONLY" ? "ANALYZED" : "PREPARED"))}>{outcomeLabel(proposal, outcome)}</StatusPill>
          </div>
          <h3 className="mt-3 text-sm font-semibold text-white">{proposal.title}</h3>
          <p className="mt-1 text-[11px] text-slate-500">Affected record: {targetName ?? label(proposal.target_type)}</p>
        </div>
        {outcome && <StatusPill tone={statusTone(outcome.status)}>{label(outcome.status)}</StatusPill>}
      </div>
      <p className="mt-4 text-xs leading-5 text-slate-300/85">{proposal.explanation}</p>
      <dl className="mt-4 grid grid-cols-2 gap-3 border-y border-white/[.06] py-3 text-xs sm:grid-cols-3">
        <div><dt className="text-[10px] uppercase tracking-[.1em] text-slate-600">Risk level</dt><dd className="mt-1 font-semibold text-slate-200">{proposal.risk_level}</dd></div>
        <div><dt className="text-[10px] uppercase tracking-[.1em] text-slate-600">Current decision</dt><dd className="mt-1 font-semibold text-slate-200">{proposal.workflow_recommendation_action ? label(proposal.workflow_recommendation_action) : proposal.executable ? "Review current intelligence" : "Review safeguard"}</dd></div>
        <div><dt className="text-[10px] uppercase tracking-[.1em] text-slate-600">Next state</dt><dd className="mt-1 font-semibold text-slate-200">{proposal.requires_confirmation ? "Awaiting your confirmation" : proposal.execution_mode === "READ_ONLY" ? "No workflow record" : "Prepared only"}</dd></div>
      </dl>
      {outcome && <p className="mt-3 text-xs leading-5 text-slate-400">{outcome.message}</p>}
      {outcome?.status === "EXECUTED" && (
        <div className="mt-3 rounded-xl border border-emerald-300/15 bg-emerald-300/[.045] p-3 text-xs leading-5 text-emerald-50/85">
          <p className="font-semibold text-emerald-200">Internal recovery workflow record created</p>
          {outcome.recovery_action_status && <p className="mt-1">Workflow status: {label(outcome.recovery_action_status)}</p>}
          {outcome.recovery_action_created_at && <p className="mt-1">Recorded: {new Date(outcome.recovery_action_created_at).toLocaleString()}</p>}
          {outcome.workflow_effect && <p className="mt-1 text-emerald-100/75">{outcome.workflow_effect}</p>}
        </div>
      )}
      {proposal.limitations.length > 0 && (
        <ul className="mt-3 space-y-1 text-[11px] leading-5 text-slate-500">
          {proposal.limitations.map((item) => <li key={item}>Safety: {item}</li>)}
        </ul>
      )}
      {onOpenTarget && (
        <button type="button" onClick={(event) => { event.stopPropagation(); openTarget(); }} className={`${buttonStyles.primary} mt-4 w-full sm:w-auto`}>
          {outcome?.status === "EXECUTED" ? "Open affected case" : proposal.target_type === "CUSTOMER" ? "Open customer recovery workspace" : "Open case workspace"}
        </button>
      )}
      {proposal.requires_confirmation && outcome?.status === "AWAITING_CONFIRMATION" && onSelectedChange && (
        <label onClick={(event) => event.stopPropagation()} className="mt-4 flex cursor-pointer items-center gap-3 rounded-xl border border-amber-300/15 bg-amber-300/[.045] p-3 text-xs font-semibold text-amber-100">
          <input
            type="checkbox"
            checked={selected}
            onChange={(event) => onSelectedChange(event.target.checked)}
            className="h-4 w-4 rounded border-white/20 bg-transparent accent-sky-300"
          />
          Include this action in operator confirmation
        </label>
      )}
    </article>
  );
}
