"use client";

import type { ActionOutcome, ActionProposal, PriorityLevel } from "@/lib/intelligence-api";
import { buttonStyles, cx, StatusPill } from "@/components/dashboard/ui";

const label = (value: string) => value.replaceAll("_", " ");
const tone = (level: PriorityLevel) => level === "CRITICAL" ? "rose" : level === "HIGH" ? "amber" : level === "MEDIUM" ? "sky" : "slate";
const statusTone = (status: ActionOutcome["status"]) => status === "EXECUTED" ? "emerald" : status === "FAILED" || status === "NOT_EXECUTABLE" ? "rose" : status === "AWAITING_CONFIRMATION" ? "amber" : "sky";

export function ActionProposalCard({
  proposal,
  outcome,
  selected,
  onSelectedChange,
  onOpenTarget,
}: {
  proposal: ActionProposal;
  outcome?: ActionOutcome;
  selected?: boolean;
  onSelectedChange?: (selected: boolean) => void;
  onOpenTarget?: () => void;
}) {
  return (
    <article className={cx(
      "rounded-2xl border p-4 transition sm:p-5",
      proposal.risk_level === "CRITICAL" ? "border-rose-300/20 bg-rose-300/[.035]" : "border-white/[.08] bg-white/[.025]",
    )}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill tone={tone(proposal.priority)}>{proposal.priority} priority</StatusPill>
            <StatusPill tone="slate">{label(proposal.target_type)}</StatusPill>
          </div>
          <h3 className="mt-3 text-sm font-semibold text-white">{proposal.title}</h3>
          <p className="mt-1 text-[11px] text-slate-500">{label(proposal.action_type)} / {proposal.target_id}</p>
        </div>
        {outcome && <StatusPill tone={statusTone(outcome.status)}>{label(outcome.status)}</StatusPill>}
      </div>
      <p className="mt-4 text-xs leading-5 text-slate-300/85">{proposal.explanation}</p>
      <dl className="mt-4 grid grid-cols-2 gap-3 border-y border-white/[.06] py-3 text-xs sm:grid-cols-3">
        <div><dt className="text-[10px] uppercase tracking-[.1em] text-slate-600">Risk level</dt><dd className="mt-1 font-semibold text-slate-200">{proposal.risk_level}</dd></div>
        <div><dt className="text-[10px] uppercase tracking-[.1em] text-slate-600">Execution</dt><dd className="mt-1 font-semibold text-slate-200">{label(proposal.execution_mode)}</dd></div>
        <div><dt className="text-[10px] uppercase tracking-[.1em] text-slate-600">Executable</dt><dd className="mt-1 font-semibold text-slate-200">{proposal.executable ? "Yes, within safeguards" : "Advisory only"}</dd></div>
      </dl>
      {outcome && <p className="mt-3 text-xs leading-5 text-slate-400">{outcome.message}</p>}
      {proposal.limitations.length > 0 && (
        <ul className="mt-3 space-y-1 text-[11px] leading-5 text-slate-500">
          {proposal.limitations.map((item) => <li key={item}>Safety: {item}</li>)}
        </ul>
      )}
      {onOpenTarget && (
        <button type="button" onClick={onOpenTarget} className={`${buttonStyles.secondary} mt-4 w-full sm:w-auto`}>
          {proposal.target_type === "CUSTOMER" ? "Open customer workspace" : "Open case workspace"}
        </button>
      )}
      {proposal.requires_confirmation && outcome?.status === "AWAITING_CONFIRMATION" && onSelectedChange && (
        <label className="mt-4 flex cursor-pointer items-center gap-3 rounded-xl border border-amber-300/15 bg-amber-300/[.045] p-3 text-xs font-semibold text-amber-100">
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
