"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { ExternalPaymentRequest, ProviderEventEvidence, Workspace } from "./data";
import { useInvalidateOperationalData, useProviderMode } from "./queries";
import { buttonStyles, StatusPill } from "./ui";

const supported = new Set(["SEND_PAYMENT_REMINDER", "REQUEST_PAYMENT_DATE"]);
const label = (value: string) => value.replaceAll("_", " ");
const money = (value: string | number) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(value));

export function PaymentRequestPanel({ workspace }: { workspace: Workspace }) {
  const [reviewing, setReviewing] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const providerMode = useProviderMode();
  const invalidate = useInvalidateOperationalData();
  const requests = workspace.external_payment_requests ?? [];
  const latest = requests[0];
  const latestInternalAction = [...workspace.actions].sort((left, right) => new Date(right.created_at ?? 0).getTime() - new Date(left.created_at ?? 0).getTime())[0];
  const visibleRequest = latest?.status === "FAILED" && reviewing ? undefined : latest;
  const latestEvent = (workspace.provider_events ?? []).find((item) => item.payment_request_id === latest?.id);
  const eligible = Boolean(workspace.invoice && supported.has(workspace.recommendation.recommended_action) && workspace.recommendation.blockers.length === 0);

  const mutation = useMutation({
    mutationFn: async ({ path, body }: { path: string; body: Record<string, unknown> }) => {
      const response = await apiFetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }, 30_000);
      const result = await response.json().catch(() => null) as { detail?: string } | null;
      if (!response.ok) throw new Error(result?.detail ?? "The provider operation failed safely.");
      return result;
    },
    onSuccess: async () => { setConfirmed(false); setReviewing(false); await invalidate(); },
  });
  const error = mutation.error instanceof Error ? mutation.error.message : providerMode.error instanceof Error ? providerMode.error.message : null;
  const create = () => {
    if (!workspace.invoice || !confirmed || mutation.isPending) return;
    mutation.mutate({ path: `/payment-provider/cases/${workspace.case_id}/requests`, body: { operator_id: "web-operator", requested_amount: workspace.invoice.outstanding_amount, purpose: `Payment request for invoice ${workspace.invoice.number}`, operator_confirmed: true, expected_recommended_action: workspace.recommendation.recommended_action, expected_outstanding_amount: workspace.invoice.outstanding_amount } });
  };
  const applyDemoPayment = () => {
    if (!latest?.provider_reference || mutation.isPending || !window.confirm("Record this deterministic Provider Demo Mode payment event? This will persist a real local payment fact and reduce the invoice outstanding amount.")) return;
    const remaining = Number(latest.requested_amount) - Number(latest.paid_amount);
    mutation.mutate({ path: "/payment-provider/events/demo", body: { event_id: `demo_event_${latest.id}`, provider_reference: latest.provider_reference, payment_reference: `demo_payment_${latest.id}`, amount: remaining.toFixed(2), payment_date: workspace.intelligence.calculated_at, event_type: "payment_request.paid" } });
  };

  return <section className="rounded-2xl border border-violet-300/15 bg-violet-300/[.025] p-5">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-[10px] font-bold uppercase tracking-[.15em] text-violet-300">External execution boundary</p><h3 className="mt-1.5 text-lg font-semibold text-white">Operator-approved payment request</h3><p className="mt-1 text-xs leading-5 text-slate-400">A payment request is an external action, not a payment. Financial state changes only after a validated provider event.</p></div><StatusPill tone={providerMode.data?.mode === "TEST" ? "sky" : "amber"}>{providerMode.data?.label ?? "Provider mode loading"}</StatusPill></div>
    {error && <div role="alert" className="mt-4 rounded-xl border border-rose-300/20 bg-rose-300/[.06] p-3 text-xs text-rose-100"><p>{error}</p><button type="button" onClick={() => { mutation.reset(); void providerMode.refetch(); }} className="mt-2 font-semibold underline">Retry</button></div>}
    {visibleRequest ? <ExistingRequest request={visibleRequest} event={latestEvent} internalAction={latestInternalAction} busy={mutation.isPending} onApplyDemo={applyDemoPayment} onRetry={() => setReviewing(true)} /> : eligible ? reviewing ? <div className="mt-4 rounded-xl border border-white/[.08] bg-black/10 p-4">
      <div className="grid gap-3 text-xs sm:grid-cols-2"><Fact term="Customer" value={workspace.customer.name} /><Fact term="Related invoice" value={workspace.invoice?.number ?? "Unavailable"} /><Fact term="Outstanding amount" value={workspace.invoice ? money(workspace.invoice.outstanding_amount) : "Unavailable"} /><Fact term="Proposed amount" value={workspace.invoice ? money(workspace.invoice.outstanding_amount) : "Unavailable"} /><Fact term="Payment provider" value={providerMode.data?.mode === "TEST" ? "Razorpay / test mode" : "Provider Demo Mode"} /><Fact term="Purpose" value={`Request payment for ${workspace.invoice?.number}`} /><Fact term="Actionability" value="No current blocker detected" /><Fact term="Approval" value="Explicit operator confirmation required" /></div>
      <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-xl border border-violet-300/15 bg-violet-300/[.04] p-3 text-xs leading-5 text-slate-300"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} className="mt-1" />I reviewed the customer, invoice, amount, provider mode, and blockers. Create this external payment request.</label>
      <div className="mt-4 flex flex-wrap gap-2"><button type="button" disabled={mutation.isPending} onClick={() => { setReviewing(false); setConfirmed(false); }} className={buttonStyles.secondary}>Cancel</button><button type="button" disabled={!confirmed || mutation.isPending || !providerMode.data} onClick={create} className={buttonStyles.primary}>{mutation.isPending ? "Creating provider action…" : "Create payment request"}</button></div>
    </div> : <button type="button" disabled={!providerMode.data || mutation.isPending} onClick={() => setReviewing(true)} className={`${buttonStyles.primary} mt-4`}>Review payment request</button> : <p className="mt-4 rounded-xl border border-white/[.07] bg-black/10 p-4 text-xs leading-5 text-slate-400">No payment request is available for the current decision. Dispute review, promise holds, monitoring, escalation, resolved cases, and blocked recovery states remain internal or advisory.</p>}
    {!latest && <p className="mt-3 text-[11px] font-medium text-slate-500">Provider outcome not exercised for this case.</p>}
  </section>;
}

function ExistingRequest({ request, event, internalAction, busy, onApplyDemo, onRetry }: { request: ExternalPaymentRequest; event?: ProviderEventEvidence; internalAction?: Workspace["actions"][number]; busy: boolean; onApplyDemo: () => void; onRetry: () => void }) {
  const evidence = event?.evidence;
  return <div className="mt-4 space-y-4"><div className="rounded-xl border border-white/[.08] bg-black/10 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-semibold text-white">{request.provider_mode === "TEST" ? "Razorpay payment request" : "Provider demo payment request"}</p><StatusPill tone={request.status === "FAILED" ? "rose" : request.status === "PAID" ? "emerald" : "sky"}>{label(request.status)}</StatusPill></div><div className="mt-3 grid gap-3 text-xs sm:grid-cols-2"><Fact term="Request ID" value={request.id} /><Fact term="Provider reference" value={request.provider_reference ?? "Not issued"} /><Fact term="Provider status" value={label(request.status)} /><Fact term="Requested amount" value={money(request.requested_amount)} /><Fact term="Recorded payment" value={money(request.paid_amount)} /><Fact term="Operator" value={request.operator_id} /></div>{request.failure_reason && <p className="mt-3 text-xs text-rose-200">Provider failure: {request.failure_reason}</p>}{request.provider_url && <a href={request.provider_url} target="_blank" rel="noreferrer" className="mt-3 inline-block text-xs font-semibold text-sky-300">Open provider test link ↗</a>}{request.status === "FAILED" && <button type="button" disabled={busy} onClick={onRetry} className={`${buttonStyles.secondary} mt-4`}>Review a new request</button>}{request.provider_mode === "DEMO" && ["ACTIVE", "PARTIALLY_PAID"].includes(request.status) && <button type="button" disabled={busy} onClick={onApplyDemo} className={`${buttonStyles.success} mt-4`}>{busy ? "Applying provider event…" : "Record demo payment event"}</button>}</div>
    <div className="grid gap-2 sm:grid-cols-2"><Evidence title="External payment request" detail={`Source: ${request.provider_mode === "DEMO" ? "Provider Demo Mode" : "Razorpay Test Mode"} · Request ${request.provider_reference ?? request.id} · financial mutation: none`} /><Evidence title="Entity scope" detail={`Customer ${request.customer_id.slice(0, 8)} · Case ${request.case_id.slice(0, 8)} · Invoice ${request.invoice_id.slice(0, 8)}`} /></div>
    <ProviderLifecycle request={request} event={event} internalAction={internalAction} />
    {evidence && <div className="grid gap-2 sm:grid-cols-2"><Evidence title="Provider event" detail={`Event ${event?.provider_event_id ?? "—"} · received ${new Date(event?.received_at ?? evidence.received_at ?? "").toLocaleString()} · ${label(evidence.verification_state ?? "validation recorded")}`} /><Evidence title="Event integrity" detail={`Idempotency ${evidence.idempotency_key ?? "not reported"} · signature ${label(evidence.signature_verification ?? "not reported")} · ${evidence.immutable_event_record ? "immutable record" : "persistence recorded"}`} /><Evidence title="Financial state change" detail={`${money(evidence.outstanding_before ?? 0)} → ${money(evidence.outstanding_after ?? 0)} outstanding · payment persisted`} /><Evidence title="Intelligence reassessment" detail={`Score ${evidence.score_before ?? "—"} → ${evidence.score_after ?? "—"}`} /><Evidence title="Decision reassessment" detail={`${label(evidence.recommendation_before ?? "unknown")} → ${label(evidence.recommendation_after ?? "unknown")}`} />{evidence.duplicate_replay?.ignored && <div className="rounded-xl border border-amber-300/20 bg-amber-300/[.04] p-3 sm:col-span-2"><p className="text-[10px] font-bold uppercase tracking-[.1em] text-amber-200">Duplicate provider event ignored</p><p className="mt-1.5 text-xs leading-5 text-slate-200">Original event: {evidence.duplicate_replay.original_event} · Financial mutation: none · Outstanding unchanged{evidence.duplicate_replay.outstanding_after ? ` at ${money(evidence.duplicate_replay.outstanding_after)}` : ""}</p></div>}<p className="sm:col-span-2 text-[11px] leading-5 text-slate-500">Source: {evidence.source ?? (request.provider_mode === "DEMO" ? "Provider Demo Mode" : "Razorpay Test Mode")}. {evidence.chronology}</p></div>}
  </div>;
}

function ProviderLifecycle({ request, event, internalAction }: { request: ExternalPaymentRequest; event?: ProviderEventEvidence; internalAction?: Workspace["actions"][number] }) {
  const applied = Boolean(event?.evidence);
  const failed = request.status === "FAILED";
  const stages = [
    ["Deterministic decision", "Current"],
    ["Internal workflow action", internalAction ? label(internalAction.status) : "Separate / not created"],
    ["Operator review / approval", "Confirmed"],
    ["External payment request", failed ? "Unavailable" : label(request.status)],
    ["Provider event", applied ? "Validated" : failed ? "Unavailable" : "Pending"],
    ["Financial state change", applied ? "Applied once" : "Not exercised"],
    ["Decision reassessment", applied ? "Completed" : "Not exercised"],
  ] as const;
  return <div className="rounded-xl border border-white/[.07] bg-black/10 p-3"><p className="text-[10px] font-bold uppercase tracking-[.12em] text-slate-500">External recovery lifecycle</p><ol className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">{stages.map(([name, state], index) => <li key={name} className="rounded-lg border border-white/[.06] px-3 py-2"><p className="text-[9px] font-bold uppercase tracking-[.1em] text-slate-600">{index + 1}. {name}</p><p className={`mt-1 text-[11px] font-semibold ${state === "Completed" ? "text-emerald-200" : state === "Pending" ? "text-amber-100" : "text-slate-500"}`}>{state}</p></li>)}</ol><p className="mt-3 text-[10px] leading-4 text-slate-500">Request ≠ payment. A provider event is validated before payment persistence; observed recovery does not prove causation.</p></div>;
}

function Fact({ term, value }: { term: string; value: string }) { return <div><p className="text-slate-500">{term}</p><p className="mt-1 font-medium text-slate-200">{value}</p></div>; }
function Evidence({ title, detail }: { title: string; detail: string }) { return <div className="rounded-xl border border-white/[.07] bg-black/10 p-3"><p className="text-[10px] font-bold uppercase tracking-[.1em] text-slate-500">{title}</p><p className="mt-1.5 text-xs leading-5 text-slate-200">{detail}</p></div>; }
