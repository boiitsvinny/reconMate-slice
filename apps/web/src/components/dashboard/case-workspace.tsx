"use client";

import { useEffect, useState } from "react";
import type { PriorityCase } from "./dashboard";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type Workspace = {
  customer: { name: string; strategic: boolean };
  invoice: { number: string; status: string; outstanding_amount: string; due_date: string } | null;
  recommendation: { recommended_action: string; priority: string; factual_reasons: string[]; blockers: string[]; relevant_days_overdue: number; human_approval_required: boolean; communication_signals: { intent: string; confidence: string | null }[] };
  promises: { status: string; promised_amount: string; promised_date: string }[];
  communications: { id: string; direction: string; content: string; occurred_at: string; analyses: { intent?: string }[] }[];
  actions: { id: string; status: string; recommended_action: string | null; human_approval_required: boolean; decision_reason: string | null; executed_at: string | null }[];
  audit_events: { id: string; event_type: string; occurred_at: string }[];
};

function label(value: string) { return value.replaceAll("_", " "); }
function money(value: string) { return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(value)); }

export function CaseWorkspace({ item, onClose, liveVersion, affected }: { item: PriorityCase; onClose: () => void; liveVersion: number; affected: boolean }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const reload = () => fetch(`${apiBaseUrl}/recovery/cases/${item.id}/workspace`).then(async (response) => {
    if (!response.ok) throw new Error((await response.json()).detail ?? "Unable to load the case workspace.");
    return response.json() as Promise<Workspace>;
  }).then(setWorkspace).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Unable to load workspace."));
  useEffect(() => { reload(); }, [item.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (affected) reload(); }, [affected, liveVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  async function request(url: string, body: Record<string, unknown>) {
    setBusy(true); setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}${url}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!response.ok) throw new Error((await response.json()).detail ?? "Workflow action was not accepted.");
      reload();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Workflow action failed."); }
    finally { setBusy(false); }
  }
  const latest = workspace?.actions[0];
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

  return <div className="fixed inset-0 z-50 flex justify-end bg-[#050814]/60 p-2 backdrop-blur-sm" onClick={onClose} role="presentation"><section className="h-full w-full max-w-2xl overflow-y-auto rounded-2xl border border-white/[0.12] bg-[#0d1628] p-5 shadow-2xl shadow-black/70 sm:p-7" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label={`${item.customerName} recovery workspace`}>
    <div className="flex items-start justify-between gap-4"><div><p className="text-[10px] font-semibold uppercase tracking-[.16em] text-sky-300">Operator case workspace</p><h2 className="mt-2 text-2xl font-semibold text-white">{workspace?.customer.name ?? item.customerName}</h2><p className="mt-1 text-xs text-slate-500">{workspace?.customer.strategic ? "Strategic account · " : ""}{item.customerReference}</p></div><button onClick={onClose} className="rounded-lg border border-white/10 px-2.5 py-1 text-slate-400 hover:text-white">×</button></div>
    {error && <p className="mt-5 rounded-xl border border-rose-300/15 bg-rose-300/[.06] p-3 text-sm text-rose-200">{error}</p>}
    {affected && <p className="live-enter mt-5 rounded-xl border border-sky-300/15 bg-sky-400/[.05] p-3 text-xs text-sky-200">Portfolio update detected — factual case data and recommendation refreshed.</p>}
    {!workspace && !error && <div className="mt-8 h-64 animate-pulse rounded-2xl bg-white/[.04]" />}
    {workspace && <div className="mt-6 space-y-5">
      <section className="grid gap-3 sm:grid-cols-4"><Card label="Exposure" value={workspace.invoice ? money(workspace.invoice.outstanding_amount) : "—"} /><Card label="Overdue" value={`${workspace.recommendation.relevant_days_overdue} days`} /><Card label="Invoice" value={workspace.invoice?.status ?? "—"} /><Card label="Promise" value={workspace.promises[0] ? label(workspace.promises[0].status) : "None"} /></section>
      <section className="rounded-2xl border border-sky-300/18 bg-sky-400/[.055] p-5"><p className="text-[10px] font-semibold uppercase tracking-[.15em] text-sky-300">System recommendation · advisory</p><div className="mt-2 flex flex-wrap items-center justify-between gap-3"><h3 className="text-lg font-semibold text-white">{label(workspace.recommendation.recommended_action)}</h3><span className="rounded-full border border-sky-300/20 px-2.5 py-1 text-[10px] font-bold text-sky-200">{workspace.recommendation.priority}</span></div><ul className="mt-3 space-y-1 text-sm text-slate-300">{workspace.recommendation.factual_reasons.map((reason) => <li key={reason}>• {reason}</li>)}</ul>{workspace.recommendation.blockers.length > 0 && <p className="mt-3 text-xs text-amber-200">Blockers: {workspace.recommendation.blockers.map(label).join(" · ")}</p>}<p className="mt-3 text-xs text-slate-400">Human approval {workspace.recommendation.human_approval_required ? "required" : "not required"}. Interpretation signals are supporting evidence only.</p></section>
      <section className="rounded-2xl border border-white/[.09] bg-white/[.025] p-5"><p className="text-[10px] font-semibold uppercase tracking-[.15em] text-slate-500">Operator decision</p>{!latest ? <button disabled={busy || workspace.recommendation.recommended_action === "NO_ACTION_REQUIRED"} onClick={create} className="mt-4 rounded-xl bg-sky-400 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-40">Create action from recommendation</button> : <div className="mt-3"><p className="text-sm text-slate-300">Latest action: <span className="font-semibold text-white">{label(latest.status)}</span>{latest.recommended_action && ` · ${label(latest.recommended_action)}`}</p><div className="mt-4 flex flex-wrap gap-2">{latest.status === "PENDING_APPROVAL" && <button disabled={busy} onClick={() => decision("approve")} className="rounded-lg bg-emerald-300 px-3 py-1.5 text-xs font-bold text-emerald-950">Approve</button>}{["RECOMMENDED", "PENDING_APPROVAL", "APPROVED"].includes(latest.status) && <button disabled={busy} onClick={() => decision("hold")} className="rounded-lg border border-amber-300/25 px-3 py-1.5 text-xs font-bold text-amber-200">Hold</button>}{["RECOMMENDED", "PENDING_APPROVAL", "APPROVED"].includes(latest.status) && <button disabled={busy} onClick={() => decision("reject")} className="rounded-lg border border-rose-300/25 px-3 py-1.5 text-xs font-bold text-rose-200">Reject</button>}{["RECOMMENDED", "APPROVED"].includes(latest.status) && <button disabled={busy} onClick={() => decision("execute")} className="rounded-lg bg-sky-400 px-3 py-1.5 text-xs font-bold text-slate-950">Execute simulated action</button>}</div></div>}</section>
      <section className="grid gap-5 md:grid-cols-2"><Timeline title="Recovery timeline" entries={[...workspace.actions.map((action) => `${label(action.status)} · ${action.recommended_action ? label(action.recommended_action) : "historical action"}`), ...workspace.audit_events.slice(0, 6).map((event) => label(event.event_type))]} /><Timeline title="Communication intelligence · interpreted" entries={workspace.communications.slice(0, 4).map((communication) => `${communication.direction}: ${communication.analyses[0]?.intent ? label(communication.analyses[0].intent) : "Not analysed"}`)} /></section>
    </div>}
  </section></div>;
}

function Card({ label, value }: { label: string; value: string }) { return <div className="rounded-xl border border-white/[.08] bg-white/[.025] p-3"><p className="text-[10px] uppercase tracking-[.12em] text-slate-500">{label}</p><p className="mt-1 text-sm font-semibold text-white">{value}</p></div>; }
function Timeline({ title, entries }: { title: string; entries: string[] }) { return <section className="rounded-2xl border border-white/[.08] p-4"><p className="text-xs font-semibold text-slate-200">{title}</p><ul className="mt-3 space-y-2 text-xs leading-5 text-slate-400">{entries.length ? entries.map((entry, index) => <li key={`${entry}-${index}`} className="border-l border-sky-300/25 pl-3">{entry}</li>) : <li>No recorded items.</li>}</ul></section>; }
