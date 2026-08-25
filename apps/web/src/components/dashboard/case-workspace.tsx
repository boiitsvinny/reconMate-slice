"use client";

import { useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { useCommandSession } from "@/components/intelligence/command-session";
import type { IntelligenceTransition, PriorityCase } from "./data";
import { queryKeys, useCaseWorkspace, useInvalidateOperationalData } from "./queries";
import { buttonStyles, cx, StatusPill } from "./ui";

function label(value: string) { return value.replaceAll("_", " "); }
function money(value: string) { return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(value)); }

function actionName(action: { action_type: string; recommended_action: string | null }) {
  return label(action.recommended_action ?? action.action_type);
}

function executedActionExplanation(action: { executed_at: string | null; recommendation_context: { workflow_effect?: string } | null }) {
  const executedAt = action.executed_at;
  const timestamp = executedAt ? ` at ${new Date(executedAt).toLocaleString()}` : "";
  const boundary = action.recommendation_context?.workflow_effect;
  return `ReconMate recorded this internal workflow step as executed${timestamp}.${boundary ? ` ${boundary}` : ""}`;
}

export function CaseWorkspace({ item, onClose, liveVersion, affected, transition }: { item: PriorityCase; onClose: () => void; liveVersion: number; affected: boolean; transition?: IntelligenceTransition }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const commandSession = useCommandSession();
  const workspaceQuery = useCaseWorkspace(item.id);
  const workspace = workspaceQuery.data;
  const invalidateOperationalData = useInvalidateOperationalData();
  const action = useMutation({
    mutationFn: async ({ url, body }: { url: string; body: Record<string, unknown> }) => {
      const response = await apiFetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }, 60_000);
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "Workflow action was not accepted.");
      }
      return response.json();
    },
    onSuccess: async () => { await invalidateOperationalData(); },
  });

  useEffect(() => {
    if (affected) void queryClient.invalidateQueries({ queryKey: queryKeys.workspace(item.id) });
  }, [affected, item.id, liveVersion, queryClient]);

  async function request(url: string, body: Record<string, unknown>) {
    try {
      await action.mutateAsync({ url, body });
    } catch {
      // Mutation error is rendered without discarding the current workspace.
    }
  }

  const latest = workspace?.actions.reduce((current, candidate) => {
    if (!current) return candidate;
    return new Date(candidate.created_at ?? 0).getTime() > new Date(current.created_at ?? 0).getTime() ? candidate : current;
  }, workspace.actions[0]);
  const queryError = workspaceQuery.error instanceof Error ? workspaceQuery.error.message : null;
  const mutationError = action.error instanceof Error ? action.error.message : null;
  const error = mutationError ?? (!workspace ? queryError : null);
  const busy = action.isPending;
  const runContextCommand = (command: string, context: { context_customer_id?: string; context_case_id?: string }) => {
    onClose();
    router.push("/analytics");
    void commandSession.runCommand({ command, ...context });
  };
  const create = () => {
    if (workspace && window.confirm(`Create a workflow action for ${label(workspace.recommendation.recommended_action)}?`)) {
      request(`/recovery/cases/${item.id}/actions`, { expected_recommended_action: workspace.recommendation.recommended_action });
    }
  };
  const decision = (verb: "approve" | "reject" | "hold" | "cancel" | "execute") => {
    if (!latest || !window.confirm(`${label(verb)} this simulated recovery action?`)) return;
    const reason = verb === "reject" || verb === "hold" || verb === "cancel" ? window.prompt(`Reason for ${verb}:`) : undefined;
    if ((verb === "reject" || verb === "hold" || verb === "cancel") && !reason) return;
    request(`/recovery/actions/${latest.id}/${verb}`, { operator_id: "web-operator", reason });
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-[#050814]/65 p-0 backdrop-blur-sm sm:p-2" onClick={onClose} role="presentation">
      <section className="h-full w-full max-w-2xl overflow-y-auto rounded-none border border-white/[0.12] bg-[#0d1628] p-4 pb-24 shadow-2xl shadow-black/70 sm:rounded-2xl sm:p-7" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label={`${item.customerName} recovery workspace`}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[.16em] text-sky-300">Operator case workspace</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-.035em] text-white sm:text-3xl">{workspace?.customer.name ?? item.customerName}</h2>
            <p className="mt-1 text-xs text-slate-400">Case {item.id.slice(0, 8)} / {workspace?.customer.strategic ? "Strategic account / " : ""}{item.customerReference}</p>
            {workspace?.invoice && <p className="mt-1 text-[10px] text-slate-600">Invoice {workspace.invoice.number} / current factual status {workspace.invoice.status}</p>}
          </div>
          <button onClick={onClose} className="rounded-lg border border-white/10 px-2.5 py-1 text-slate-400 transition hover:border-white/20 hover:text-white">Close</button>
        </div>
        <section className="mt-5 rounded-2xl border border-sky-300/12 bg-sky-300/[.035] p-4" aria-label="Contextual intelligence actions">
          <p className="text-[10px] font-bold uppercase tracking-[.15em] text-sky-300">Investigate with ReconMate</p>
          <h3 className="mt-1.5 text-lg font-semibold tracking-[-.02em] text-white sm:text-xl">Ask intelligence about this live context</h3>
          <p className="mt-1 text-[11px] leading-4 text-slate-500">These read the current customer or case state and open the Intelligence workspace with the correct record context.</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            <button type="button" disabled={commandSession.processing} onClick={() => runContextCommand("Analyze this customer", { context_customer_id: item.customerId })} className={buttonStyles.secondary}>Analyze customer</button>
            <button type="button" disabled={commandSession.processing} onClick={() => runContextCommand("Why is this case critical?", { context_case_id: item.id })} className={buttonStyles.secondary}>Explain recommendation</button>
            <button type="button" disabled={commandSession.processing} onClick={() => runContextCommand("Analyze this case", { context_case_id: item.id })} className={buttonStyles.secondary}>Review case intelligence</button>
          </div>
        </section>
        {error && <p className="mt-5 border border-rose-300/15 bg-rose-300/[.06] p-3 text-sm text-rose-100">{error}</p>}
        {affected && transition && (
          <section className={`live-enter mt-5 rounded-2xl border p-4 ${transition.material ? transition.change_direction === "IMPROVED" ? "border-emerald-300/20 bg-emerald-300/[.05]" : "border-amber-300/20 bg-amber-300/[.05]" : "border-sky-300/15 bg-sky-400/[.04]"}`} aria-label="Recent case intelligence transition">
            <p className="text-[10px] font-bold uppercase tracking-[.14em] text-sky-300">Cycle {transition.simulation_cycle} intelligence change</p>
            <h3 className="mt-2 text-lg font-semibold text-white">{transition.material ? transition.change_direction === "UNCHANGED" ? "Decision changed" : `Situation ${transition.change_direction.toLowerCase()}` : "No material decision change"}</h3>
            <p className="mt-2 text-xs leading-5 text-slate-300">{transition.what_changed}</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <div><p className="text-[9px] font-bold uppercase tracking-[.12em] text-slate-500">Why intelligence changed</p><p className="mt-1 text-[11px] leading-5 text-slate-400">{transition.why_intelligence_changed}</p></div>
              <div><p className="text-[9px] font-bold uppercase tracking-[.12em] text-slate-500">Decision impact</p><p className="mt-1 text-[11px] leading-5 text-slate-400">{transition.decision_impact}</p></div>
            </div>
          </section>
        )}
        {affected && !transition && <p className="live-enter mt-5 border border-sky-300/15 bg-sky-400/[.05] p-3 text-xs text-sky-200">Portfolio update detected. Factual case data and recommendation refreshed.</p>}
        {!workspace && !error && <div className="mt-8 h-64 animate-pulse rounded-2xl bg-white/[.04]" />}
        {workspace && (
          <div className="mt-6 space-y-5">
            <section className="grid gap-3 sm:grid-cols-4">
              <Card label="Exposure" value={workspace.invoice ? money(workspace.invoice.outstanding_amount) : "-"} />
              <Card label="Overdue" value={`${workspace.recommendation.relevant_days_overdue} days`} />
              <Card label="Invoice" value={workspace.invoice?.status ?? "-"} />
              <Card label="Promise" value={workspace.promises[0] ? label(workspace.promises[0].status) : "None"} />
            </section>
            <section className="rounded-2xl border border-sky-300/25 bg-sky-400/[.07] p-5 shadow-[0_16px_35px_rgba(14,165,233,.07)]">
              <p className="text-[10px] font-semibold uppercase tracking-[.15em] text-sky-300">Recommended operator next step</p>
              <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
                <h3 className="text-xl font-semibold tracking-[-.025em] text-white">{label(workspace.recommendation.recommended_action)}</h3>
                <StatusPill tone="sky">{workspace.recommendation.priority}</StatusPill>
              </div>
              <div className="mt-4 rounded-xl border border-white/[.07] bg-black/10 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[10px] font-bold uppercase tracking-[.12em] text-slate-500">Current case risk assessment</p>
                  <p className="text-xs font-semibold text-white">{workspace.intelligence.level} / {workspace.intelligence.score} of 100</p>
                </div>
                {(workspace.intelligence.factors.length > 0 || workspace.intelligence.signals.length > 0) ? (
                  <ul className="mt-3 space-y-2">
                    {(workspace.intelligence.factors.length ? workspace.intelligence.factors : workspace.intelligence.signals).slice(0, 2).map((factor) => <li key={`${factor.title}-${factor.explanation}`} className="text-xs leading-5 text-slate-400"><span className="font-semibold text-slate-200">{factor.title}:</span> {factor.explanation}</li>)}
                  </ul>
                ) : <p className="mt-3 text-xs leading-5 text-slate-400">No material risk factor is present in the current case facts.</p>}
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-300">{workspace.recommendation.operator_explanation}</p>
              <div className="mt-4 grid gap-3 border-t border-sky-200/10 pt-4 sm:grid-cols-2">
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-[.12em] text-sky-200/70">Operator step</p>
                  <p className="mt-1.5 text-xs leading-5 text-slate-300">{workspace.recommendation.operator_next_step}</p>
                </div>
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-[.12em] text-sky-200/70">If you proceed</p>
                  <p className="mt-1.5 text-xs leading-5 text-slate-300">{workspace.recommendation.workflow_effect}</p>
                </div>
              </div>
              <div className="mt-4 border-t border-sky-200/10 pt-3">
                <p className="text-xs font-semibold text-slate-200">Why ReconMate recommends this</p>
                <ul className="mt-2 space-y-1 text-xs leading-5 text-slate-400">{workspace.recommendation.factual_reasons.map((reason) => <li key={reason}>- {reason}</li>)}</ul>
              </div>
              {workspace.recommendation.blockers.length > 0 && <p className="mt-3 text-xs text-amber-200">Blockers: {workspace.recommendation.blockers.map(label).join(" / ")}</p>}
              <p className="mt-3 text-xs text-slate-400">Human approval {workspace.recommendation.human_approval_required ? "required" : "not required"}. Interpretation signals are supporting evidence only.</p>
            </section>
            <section className="rounded-2xl border border-white/[.09] bg-white/[.025] p-5">
              <p className="text-[10px] font-semibold uppercase tracking-[.15em] text-slate-500">Operator decision</p>
              <h3 className="mt-1.5 text-lg font-semibold tracking-[-.02em] text-white sm:text-xl">Choose the controlled workflow response</h3>
              <p className="mt-1 text-[11px] leading-4 text-slate-500">Creating an action records internal recovery work. It does not contact the customer or modify financial facts automatically.</p>
              {!latest ? (
                <button disabled={busy || workspace.recommendation.recommended_action === "NO_ACTION_REQUIRED"} onClick={create} className={cx("mt-4", buttonStyles.primary)}>{busy ? "Creating internal action..." : "Create internal action from recommendation"}</button>
              ) : (
                <div className="mt-4 rounded-xl border border-white/[.08] bg-black/10 p-4">
                  {latest.status === "EXECUTED" ? (
                    <div>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-[10px] font-bold uppercase tracking-[.13em] text-emerald-300">Latest action completed</p>
                        <StatusPill tone="emerald">Executed</StatusPill>
                      </div>
                      <h4 className="mt-2 text-base font-semibold text-white">{actionName(latest)}</h4>
                      <p className="mt-2 text-xs leading-5 text-slate-300">{executedActionExplanation(latest)}</p>
                    </div>
                  ) : (
                    <div>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-[10px] font-bold uppercase tracking-[.13em] text-sky-300">Latest workflow action</p>
                        <StatusPill tone="sky">{label(latest.status)}</StatusPill>
                      </div>
                      <h4 className="mt-2 text-base font-semibold text-white">{actionName(latest)}</h4>
                      <p className="mt-2 text-xs leading-5 text-slate-400">This is an internal recovery workflow record. Its current status is {label(latest.status).toLowerCase()}.</p>
                      {latest.decision_reason && <p className="mt-2 text-xs leading-5 text-slate-400">Operator reason: {latest.decision_reason}</p>}
                    </div>
                  )}
                  <div className="mt-4 flex flex-wrap gap-2">
                    {latest.status === "PENDING_APPROVAL" && <button disabled={busy} onClick={() => decision("approve")} className={buttonStyles.success}>Approve</button>}
                    {["RECOMMENDED", "PENDING_APPROVAL", "APPROVED"].includes(latest.status) && <button disabled={busy} onClick={() => decision("hold")} className={buttonStyles.warning}>Hold</button>}
                    {["RECOMMENDED", "PENDING_APPROVAL", "APPROVED"].includes(latest.status) && <button disabled={busy} onClick={() => decision("reject")} className={buttonStyles.danger}>Reject</button>}
                    {["RECOMMENDED", "APPROVED"].includes(latest.status) && <button disabled={busy} onClick={() => decision("execute")} className={buttonStyles.primary}>Execute simulated action</button>}
                  </div>
                </div>
              )}
            </section>
          </div>
        )}
      </section>
    </div>
  );
}

function Card({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/[.08] bg-white/[.025] p-3">
      <p className="text-[10px] uppercase tracking-[.12em] text-slate-500">{label}</p>
      <p className="mt-1 text-sm font-semibold text-white">{value}</p>
    </div>
  );
}
