"use client";

import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { useCommandSession } from "@/components/intelligence/command-session";
import { ReminderArtifact } from "@/components/intelligence/reminder-artifact";
import type { ReminderArtifact as ReminderArtifactData } from "@/lib/intelligence-api";
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
  const [reviewingRecommendation, setReviewingRecommendation] = useState(false);
  const [reminderDraft, setReminderDraft] = useState<ReminderArtifactData | null>(null);
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
      return true;
    } catch {
      // Mutation error is rendered without discarding the current workspace.
      return false;
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
  const create = async () => {
    if (!workspace) return;
    const created = await request(`/recovery/cases/${item.id}/actions`, { expected_recommended_action: workspace.recommendation.recommended_action });
    if (created) setReviewingRecommendation(false);
  };
  const prepareReminder = () => {
    if (!workspace?.invoice || workspace.recommendation.recommended_action !== "SEND_PAYMENT_REMINDER") return;
    const invoice = workspace.invoice;
    const amount = Number(invoice.outstanding_amount).toFixed(2);
    setReminderDraft({
      status: "PREPARED_FOR_REVIEW", customer_name: workspace.customer.name, account_reference: item.customerReference,
      invoices: [{ invoice_number: invoice.number, outstanding_amount: invoice.outstanding_amount, due_date: invoice.due_date, days_overdue: workspace.recommendation.relevant_days_overdue }],
      total_outstanding: invoice.outstanding_amount, promise_state: "NONE", dispute_state: "NONE", intended_channel: "Operator-selected channel",
      purpose: "Request payment status and expected resolution", tone: "Professional payment-status follow-up", prepared_at: new Date().toISOString(),
      body: `Hello ${workspace.customer.name},\n\nOur records show invoice ${invoice.number} with an outstanding balance of INR ${amount}. The invoice was due on ${invoice.due_date} and is ${workspace.recommendation.relevant_days_overdue} days overdue. Please confirm the current payment status and expected resolution date.\n\nThank you.`,
      reason: "The current recommendation is a payment reminder and no active promise or dispute blocks operator-reviewed outreach.",
    });
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
              <Card label="Invoice status" value={workspace.invoice?.status ?? "-"} />
              <Card label="Recovery state" value={label(workspace.workflow.recovery_state)} />
            </section>
            <section className="rounded-2xl border border-sky-300/25 bg-sky-400/[.07] p-5 shadow-[0_16px_35px_rgba(14,165,233,.07)]">
              <p className="text-[10px] font-semibold uppercase tracking-[.15em] text-sky-300">Recommended operator next step</p>
              <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
                <h3 className="text-xl font-semibold tracking-[-.025em] text-white">{label(workspace.recommendation.recommended_action)}</h3>
                <StatusPill tone="sky">{workspace.recommendation.priority}</StatusPill>
              </div>
              <div className="mt-4 rounded-xl border border-white/[.07] bg-black/10 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[10px] font-bold uppercase tracking-[.12em] text-slate-500">Current intelligence score</p>
                  <p className="text-xs font-semibold text-white">{workspace.intelligence.score}/100 / {workspace.intelligence.level}</p>
                </div>
                <p className="mt-1 text-[10px] text-slate-500">Evaluated for operating date {workspace.intelligence.calculated_at}.{workspace.intelligence.raw_score > 100 ? ` Raw weighted score ${workspace.intelligence.raw_score}; displayed score capped at 100.` : ""}</p>
                {(workspace.intelligence.factors.length > 0 || workspace.intelligence.signals.length > 0) ? (
                  <ul className="mt-3 space-y-2">
                    {(workspace.intelligence.factors.length ? workspace.intelligence.factors : workspace.intelligence.signals).slice(0, 2).map((factor) => <li key={`${factor.title}-${factor.explanation}`} className="text-xs leading-5 text-slate-400"><span className="font-semibold text-slate-200">{factor.title}:</span> {factor.explanation}</li>)}
                  </ul>
                ) : <p className="mt-3 text-xs leading-5 text-slate-400">No material risk factor is present in the current case facts.</p>}
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-300">{workspace.recommendation.operator_explanation}</p>
              <div className="mt-3 grid gap-3 rounded-xl border border-white/[.07] bg-black/10 p-3 sm:grid-cols-2"><div><p className="text-[9px] font-bold uppercase tracking-[.12em] text-slate-500">Stored workflow priority</p><p className="mt-1 text-xs font-semibold text-slate-200">{workspace.workflow.stored_priority} / {label(workspace.workflow.recovery_state)}</p></div><div><p className="text-[9px] font-bold uppercase tracking-[.12em] text-slate-500">Current recommended action</p><p className="mt-1 text-xs font-semibold text-slate-200">{label(workspace.recommendation.recommended_action)}</p></div></div>
              {workspace.workflow.stored_priority !== workspace.intelligence.level && <p className="mt-2 text-[11px] leading-5 text-slate-400"><span className="font-semibold text-slate-200">Why these differ:</span> current intelligence is recalculated from today’s persisted facts; stored workflow priority records the case’s existing operational state until an operator updates it.</p>}
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
              {workspace.recommendation.recommended_action === "SEND_PAYMENT_REMINDER" && !reminderDraft && <button type="button" onClick={prepareReminder} className={`${buttonStyles.primary} mt-4`}>Prepare reminder draft</button>}
              {reminderDraft && <ReminderArtifact artifact={reminderDraft} />}
            </section>
            <section className="rounded-2xl border border-white/[.09] bg-white/[.025] p-5">
              <p className="text-[10px] font-semibold uppercase tracking-[.15em] text-slate-500">Operator decision</p>
              <h3 className="mt-1.5 text-lg font-semibold tracking-[-.02em] text-white sm:text-xl">Choose the controlled workflow response</h3>
              <p className="mt-1 text-[11px] leading-4 text-slate-500">Creating an action records internal recovery work. It does not contact the customer or modify financial facts automatically.</p>
              {!latest ? (
                workspace.recommendation.recommended_action === "NO_ACTION_REQUIRED" ? (
                  <div className="mt-4 rounded-xl border border-white/[.08] bg-black/10 p-4"><p className="text-sm font-semibold text-slate-200">Analysis only — no workflow action available</p><p className="mt-1 text-xs leading-5 text-slate-500">The current factual recommendation requires monitoring only, so ReconMate will not create unnecessary recovery work.</p></div>
                ) : reviewingRecommendation ? (
                  <div className="mt-4 rounded-xl border border-sky-300/20 bg-sky-300/[.04] p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-[10px] font-bold uppercase tracking-[.13em] text-sky-300">Prepared action review</p><StatusPill tone={workspace.recommendation.human_approval_required ? "amber" : "sky"}>{workspace.recommendation.human_approval_required ? "Approval required" : "Operator controlled"}</StatusPill></div>
                    <h4 className="mt-2 text-base font-semibold text-white">{label(workspace.recommendation.recommended_action)}</h4>
                    <dl className="mt-3 grid gap-3 text-xs sm:grid-cols-2"><div><dt className="text-slate-500">Account / invoice</dt><dd className="mt-1 text-slate-200">{workspace.customer.name} / {workspace.invoice?.number ?? "Account-level case"}</dd></div><div><dt className="text-slate-500">Current exposure</dt><dd className="mt-1 text-slate-200">{workspace.invoice ? money(workspace.invoice.outstanding_amount) : "-"}</dd></div><div><dt className="text-slate-500">Internal workflow type</dt><dd className="mt-1 text-slate-200">{label(workspace.recommendation.recommended_action)}</dd></div><div><dt className="text-slate-500">Result if prepared</dt><dd className="mt-1 text-slate-200">{workspace.recommendation.human_approval_required ? "Pending operator approval" : "Recommended internal action"}</dd></div></dl>
                    <p className="mt-3 text-xs leading-5 text-slate-300">{workspace.recommendation.workflow_effect}</p>
                    {workspace.recommendation.blockers.length > 0 && <p className="mt-2 text-xs text-amber-200">Current guardrail: {workspace.recommendation.blockers.map(label).join(" / ")}. The prepared action remains bounded by this condition.</p>}
                    <p className="mt-2 text-[11px] text-slate-500">Internal record only — no customer communication, payment, promise, invoice, or dispute fact will be changed.</p>
                    <div className="mt-4 flex flex-wrap gap-2"><button type="button" disabled={busy} onClick={() => setReviewingRecommendation(false)} className={buttonStyles.secondary}>Cancel review</button><button type="button" disabled={busy} onClick={() => void create()} className={buttonStyles.primary}>{busy ? "Preparing internal action..." : "Prepare internal workflow action"}</button></div>
                  </div>
                ) : (
                  <button type="button" disabled={busy} onClick={() => setReviewingRecommendation(true)} className={cx("mt-4", buttonStyles.primary)}>Review recommended action</button>
                )
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
                      <p className="mt-1 text-[11px] text-slate-500">Created {latest.created_at ? new Date(latest.created_at).toLocaleString() : "in the current operator session"} / approval state {label(latest.approval_status)}</p>
                      {latest.decision_reason && <p className="mt-2 text-xs leading-5 text-slate-400">Operator reason: {latest.decision_reason}</p>}
                      {latest.decision_at && <p className="mt-1 text-[11px] text-slate-500">Decision recorded {new Date(latest.decision_at).toLocaleString()}{latest.decision_by ? ` by ${latest.decision_by}` : ""}.</p>}
                    </div>
                  )}
                  <div className="mt-4 flex flex-wrap gap-2">
                    {latest.status === "PENDING_APPROVAL" && <button disabled={busy} onClick={() => decision("approve")} className={buttonStyles.success}>Approve internal action</button>}
                    {["RECOMMENDED", "PENDING_APPROVAL", "APPROVED"].includes(latest.status) && <button disabled={busy} onClick={() => decision("hold")} className={buttonStyles.warning}>Hold</button>}
                    {["RECOMMENDED", "PENDING_APPROVAL", "APPROVED"].includes(latest.status) && <button disabled={busy} onClick={() => decision("reject")} className={buttonStyles.danger}>Reject</button>}
                    {["RECOMMENDED", "PENDING_APPROVAL", "APPROVED", "HELD", "REJECTED"].includes(latest.status) && <button disabled={busy} onClick={() => decision("cancel")} className={buttonStyles.secondary}>Cancel workflow action</button>}
                    {["RECOMMENDED", "APPROVED"].includes(latest.status) && <button disabled={busy} onClick={() => decision("execute")} className={buttonStyles.primary}>Record simulated internal action</button>}
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
