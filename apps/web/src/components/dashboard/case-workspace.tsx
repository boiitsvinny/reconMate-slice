"use client";

import { useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { apiUrl } from "@/lib/api";
import { useCommandSession } from "@/components/intelligence/command-session";
import type { PriorityCase } from "./data";
import { queryKeys, useCaseWorkspace, useInvalidateOperationalData } from "./queries";
import { buttonStyles, cx, StatusPill } from "./ui";

function label(value: string) { return value.replaceAll("_", " "); }
function money(value: string) { return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(value)); }

export function CaseWorkspace({ item, onClose, liveVersion, affected }: { item: PriorityCase; onClose: () => void; liveVersion: number; affected: boolean }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const commandSession = useCommandSession();
  const workspaceQuery = useCaseWorkspace(item.id);
  const workspace = workspaceQuery.data;
  const invalidateOperationalData = useInvalidateOperationalData();
  const action = useMutation({
    mutationFn: async ({ url, body }: { url: string; body: Record<string, unknown> }) => {
      const response = await fetch(apiUrl(url), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
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

  const latest = workspace?.actions[0];
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
        {affected && <p className="live-enter mt-5 border border-sky-300/15 bg-sky-400/[.05] p-3 text-xs text-sky-200">Portfolio update detected. Factual case data and recommendation refreshed.</p>}
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
              <p className="mt-3 text-sm leading-6 text-slate-300">{workspace.recommendation.operator_explanation}</p>
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
                <div className="mt-3">
                  <p className="text-sm text-slate-300">Latest action: <span className="font-semibold text-white">{label(latest.status)}</span>{latest.recommended_action && ` / ${label(latest.recommended_action)}`}</p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {latest.status === "PENDING_APPROVAL" && <button disabled={busy} onClick={() => decision("approve")} className={buttonStyles.success}>Approve</button>}
                    {["RECOMMENDED", "PENDING_APPROVAL", "APPROVED"].includes(latest.status) && <button disabled={busy} onClick={() => decision("hold")} className={buttonStyles.warning}>Hold</button>}
                    {["RECOMMENDED", "PENDING_APPROVAL", "APPROVED"].includes(latest.status) && <button disabled={busy} onClick={() => decision("reject")} className={buttonStyles.danger}>Reject</button>}
                    {["RECOMMENDED", "APPROVED"].includes(latest.status) && <button disabled={busy} onClick={() => decision("execute")} className={buttonStyles.primary}>Execute simulated action</button>}
                  </div>
                </div>
              )}
            </section>
            <section className="grid gap-5 md:grid-cols-2">
              <Timeline eyebrow="Factual workflow" title="Recovery timeline" detail="Persisted actions and audited case changes" entries={[...workspace.actions.map((action) => `${label(action.status)} / ${action.recommended_action ? label(action.recommended_action) : "historical action"}`), ...workspace.audit_events.slice(0, 6).map((event) => label(event.event_type))]} />
              <Timeline eyebrow="Interpreted context" title="Communication intelligence" detail="Bounded intent signals; not verified financial facts" entries={workspace.communications.slice(0, 4).map((communication) => `${communication.direction}: ${communication.analyses[0]?.intent ? label(communication.analyses[0].intent) : "Not analysed"}`)} />
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

function Timeline({ eyebrow, title, detail, entries }: { eyebrow: string; title: string; detail: string; entries: string[] }) {
  return (
    <section className="rounded-xl border border-white/[.08] p-4">
      <p className="text-[9px] font-bold uppercase tracking-[.13em] text-sky-300/70">{eyebrow}</p>
      <h3 className="mt-1.5 text-base font-semibold tracking-[-.015em] text-white">{title}</h3>
      <p className="mt-1 text-[10px] leading-4 text-slate-600">{detail}</p>
      <ul className="mt-3 space-y-2 text-xs leading-5 text-slate-400">{entries.length ? entries.map((entry, index) => <li key={`${entry}-${index}`} className="border-l border-sky-300/25 pl-3">{entry}</li>) : <li>No recorded items.</li>}</ul>
    </section>
  );
}
