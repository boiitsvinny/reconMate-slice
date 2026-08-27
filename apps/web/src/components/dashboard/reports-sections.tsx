"use client";

import { useState } from "react";
import type { IntelligenceResult, PortfolioIntelligence } from "@/lib/intelligence-api";
import { labeledTimestamp } from "@/lib/time";
import type { BatchRecoveryProof, ExternalPaymentRequest, LatestIntelligenceCycle, PriorityCase, Recovery, RecoveryAction, SimulationEvent } from "./data";
import { formatMoney } from "./data";
import { buttonStyles, Panel, SectionHeader, StatusPill } from "./ui";

type ReportProps = {
  recovery: Recovery;
  intelligence: PortfolioIntelligence;
  latestCycle: LatestIntelligenceCycle | null;
  events: SimulationEvent[];
  queue: PriorityCase[];
  actions: RecoveryAction[];
  paymentRequests: ExternalPaymentRequest[];
  batchRecovery: BatchRecoveryProof;
  onSelectCase: (item: PriorityCase) => void;
};

const label = (value: string) => value.replaceAll("_", " ");
const riskTone = (level: IntelligenceResult["level"]) => level === "CRITICAL" ? "rose" : level === "HIGH" ? "amber" : level === "MEDIUM" ? "sky" : "slate";

export function RecoveryEvidenceReport(props: ReportProps) {
  const casesByCustomer = new Map<string, PriorityCase>();
  const casesById = new Map(props.queue.map((item) => [item.id, item]));
  for (const item of props.queue) if (!casesByCustomer.has(item.customerId) || item.recommendationPriority === "CRITICAL") casesByCustomer.set(item.customerId, item);
  const intelligenceByCustomer = new Map(props.intelligence.customers.map((item) => [item.entity_id, item]));
  return <div className="space-y-6"><BatchRecoveryProofPanel {...props} casesById={casesById} /><ExecutiveSnapshot {...props} /><MaterialChanges {...props} casesByCustomer={casesByCustomer} casesById={casesById} /><DecisionReport {...props} casesByCustomer={casesByCustomer} /><DeliberateRestraint {...props} casesByCustomer={casesByCustomer} /><OperatorActivity {...props} casesById={casesById} /><OutstandingExceptions {...props} intelligenceByCustomer={intelligenceByCustomer} casesById={casesById} /></div>;
}

function BatchRecoveryProofPanel({ batchRecovery: proof, casesById, onSelectCase }: ReportProps & { casesById: Map<string, PriorityCase> }) {
  const actionOutcomes = [
    ["Proposed / planned", proof.action_outcomes.recommended + proof.action_outcomes.planned],
    ["Workflow requests awaiting approval", proof.action_outcomes.pending_approval],
    ["Approved", proof.action_outcomes.approved],
    ["Held", proof.action_outcomes.held],
    ["Rejected", proof.action_outcomes.rejected],
    ["Executed", proof.action_outcomes.executed],
    ["Requests created", proof.action_outcomes.payment_requests_created],
    ["Provider events", proof.action_outcomes.provider_events_received],
    ["Payments persisted", proof.action_outcomes.payments_persisted],
  ] as const;
  return <Panel className="proof-hero overflow-hidden border-sky-300/25 shadow-[0_24px_65px_rgba(2,132,199,.08)]">
    <SectionHeader eyebrow="Batch recovery proof" title="Measured money movement across the overdue portfolio" detail="A read-only reconciliation of persisted invoice balances and payment records, with stopping rules and operator outcomes in the same scope." prominent />
    <div className="flex flex-wrap gap-x-5 gap-y-2 border-y border-white/[.06] bg-sky-300/[.025] px-5 py-3 text-[11px] text-slate-400 sm:px-6">
      <span><strong className="text-slate-200">Scope</strong> {proof.scope.customer_count} customers · {proof.scope.invoice_count} invoices · {proof.scope.case_count} cases</span>
      <span><strong className="text-slate-200">Source</strong> {proof.scope.provenance}</span>
    </div>
    <div className="grid gap-px bg-white/[.06] lg:grid-cols-[1fr_auto_1fr_auto_1fr_.8fr] lg:items-stretch">
      <ProofAmount label="Starting overdue exposure" value={proof.reconciliation.starting_overdue_exposure} detail="Current balance plus qualifying observed payments" meta={proof.metric_metadata.starting_overdue_exposure} />
      <span className="hidden place-items-center bg-[#08111f] px-1 text-xl text-sky-300 lg:grid">−</span>
      <ProofAmount label="Observed post-due recovery" value={proof.reconciliation.observed_recovery} detail={`${proof.reconciliation.qualifying_payment_count} persisted payment record(s)`} tone="emerald" meta={proof.metric_metadata.observed_recovery} />
      <span className="hidden place-items-center bg-[#08111f] px-1 text-xl text-sky-300 lg:grid">=</span>
      <ProofAmount label="Remaining overdue" value={proof.reconciliation.remaining_overdue_exposure} detail={`${proof.reconciliation.remaining_open_overdue_invoice_count} invoice(s) remain open`} tone="rose" meta={proof.metric_metadata.remaining_overdue_exposure} />
      <ProofAmount label="Observed post-due recovery rate" value={`${proof.reconciliation.recovery_rate}%`} detail={proof.reconciliation.equation_holds ? "Reconciliation verified" : "Reconciliation exception"} tone={proof.reconciliation.equation_holds ? "emerald" : "rose"} money={false} meta={proof.metric_metadata.recovery_rate} />
    </div>
    <div className="border-b border-white/[.06] bg-black/10 px-5 py-3 sm:px-6"><p className="text-[10px] font-bold uppercase tracking-[.12em] text-amber-100">No causal attribution claimed</p><p className="mt-1 text-[11px] leading-5 text-slate-400">{proof.reconciliation.measurement_note}</p></div>
    <div className="grid gap-px bg-white/[.06] sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      <ReportMetric label="Accounts fully recovered" value={String(proof.reconciliation.fully_recovered_account_count)} detail="Customers · overdue cohort" tone="emerald" />
      <ReportMetric label="Accounts partially recovered" value={String(proof.reconciliation.partially_recovered_account_count)} detail="Customers · overdue cohort" tone="emerald" />
      <ReportMetric label="Invoices fully recovered" value={String(proof.reconciliation.recovered_invoice_count)} detail="Invoices · observed window" tone="emerald" />
      <ReportMetric label="Invoices partially recovered" value={String(proof.reconciliation.partially_recovered_invoice_count)} detail="Invoices · observed window" tone="emerald" />
      <ReportMetric label="Current recovery holds" value={String(proof.stopping_rules.deliberate_hold_count)} detail={`${proof.stopping_rules.active_dispute_hold_count} dispute · ${proof.stopping_rules.active_promise_hold_count} promise · ${proof.stopping_rules.other_blocked_case_count} other`} tone="sky" />
      <ReportMetric label="Unique unresolved exceptions" value={String(proof.stopping_rules.unresolved_exception_count)} detail={`${proof.stopping_rules.approval_required_case_count} recommendations require operator approval`} tone="amber" />
    </div>
    <div className="border-t border-white/[.06] bg-[#08111f] px-5 py-3 text-[11px] leading-5 text-slate-400 sm:px-6"><strong className="text-slate-200">Exception decomposition:</strong> {proof.stopping_rules.unresolved_exception_categories.elevated_open_cases} elevated open cases · {proof.stopping_rules.unresolved_exception_categories.broken_promise_cases} broken-promise cases · {proof.stopping_rules.unresolved_exception_categories.active_dispute_cases} active-dispute cases · {proof.stopping_rules.unresolved_exception_categories.workflow_requests_awaiting_approval} workflow requests awaiting approval. {proof.stopping_rules.exception_categories_overlap ? "Categories overlap; the headline is a deduplicated case total." : "Categories are mutually exclusive in this snapshot."} Resolved/paid cases excluded from active recovery: {proof.stopping_rules.resolved_or_paid_case_count}.</div>
    <div className="grid gap-px border-t border-white/[.06] bg-white/[.06] xl:grid-cols-2">
      <section className="bg-[#08111f] p-5 sm:p-6">
        <p className="text-[10px] font-bold uppercase tracking-[.14em] text-sky-200">Persisted action and outcome chain</p>
        <div className="mt-4 flex flex-wrap gap-2">{actionOutcomes.map(([name, count]) => <span key={name} className="rounded-full border border-white/[.08] bg-white/[.025] px-3 py-1.5 text-xs text-slate-300"><strong className="mr-1.5 tabular-nums text-white">{count}</strong>{name}</span>)}</div>
        {proof.action_outcomes.duplicate_provider_events_ignored > 0 && <p className="mt-4 text-xs text-emerald-200">{proof.action_outcomes.duplicate_provider_events_ignored} duplicate provider event(s) ignored; no second financial mutation was counted.</p>}
        {proof.action_outcomes.payment_requests_created === 0 && proof.action_outcomes.provider_events_received === 0 && <p className="mt-4 text-xs text-slate-500">No provider-demo outcome has been exercised in the current demo state. The persisted payments above are not being presented as provider events.</p>}
      </section>
      <section className="bg-[#08111f] p-5 sm:p-6">
        <p className="text-[10px] font-bold uppercase tracking-[.14em] text-sky-200">Same-scope baseline</p>
        <div className="mt-3 grid grid-cols-3 gap-3"><BaselineValue value={proof.baseline.age_only_target_count} label="Age-only targets" /><BaselineValue value={proof.baseline.reconmate_immediate_action_count} label="ReconMate actions" /><BaselineValue value={proof.baseline.blocker_violations_avoided} label="Unsafe attempts avoided" /></div>
        <p className="mt-4 text-[11px] leading-5 text-slate-500">{proof.baseline.limitation}</p>
      </section>
    </div>
    <div className="grid gap-px border-t border-white/[.06] bg-white/[.06] xl:grid-cols-2">
      <details className="group bg-[#08111f] p-5 sm:p-6">
        <summary className="cursor-pointer list-none text-sm font-semibold text-white">Payment evidence <span className="ml-2 text-xs font-normal text-slate-500">{proof.payment_evidence.length} records · expand audit trail</span></summary>
        <div className="mt-3 flex flex-wrap gap-2">{proof.payment_provenance.map((item) => <span key={item.source} className="rounded-full border border-white/[.07] px-2.5 py-1 text-[10px] text-slate-400">{item.source}: {item.payment_count} payments · {formatMoney(item.amount)}</span>)}</div>
        <div className="mt-4 max-h-80 space-y-2 overflow-y-auto pr-2">{proof.payment_evidence.map((payment) => {
          const recoveryCase = payment.case_id ? casesById.get(payment.case_id) : undefined;
          return <article key={payment.payment_id} className="rounded-xl border border-white/[.07] bg-white/[.02] p-3"><div className="flex flex-wrap items-start justify-between gap-2"><div><p className="text-xs font-semibold text-white">{payment.invoice_number} · {formatMoney(payment.amount)}</p><p className="mt-1 text-[10px] text-slate-500">{payment.payment_date} · {payment.provenance}</p></div>{recoveryCase && <button type="button" onClick={() => onSelectCase(recoveryCase)} className="text-[11px] font-semibold text-sky-300">Open case →</button>}</div><p className="mt-2 break-all text-[10px] leading-5 text-slate-400">Payment {payment.provider_payment_reference ?? payment.payment_reference ?? payment.payment_id}{payment.event_reference ? ` · Event ${payment.event_reference}` : ""}{payment.request_reference ? ` · Request ${payment.request_reference}` : ""}</p>{payment.outstanding_before !== null && payment.outstanding_after !== null && <p className="mt-1 text-[11px] text-emerald-200">Outstanding {formatMoney(payment.outstanding_before)} → {formatMoney(payment.outstanding_after)}</p>}</article>;
        })}{!proof.payment_evidence.length && <p className="py-5 text-xs text-slate-500">No qualifying post-due payment records exist in this batch.</p>}</div>
      </details>
      <details className="group bg-[#08111f] p-5 sm:p-6">
        <summary className="cursor-pointer list-none text-sm font-semibold text-white">Stopping-rule evidence <span className="ml-2 text-xs font-normal text-slate-500">{proof.stopping_rules.hold_evidence.length} records · recovery intentionally withheld</span></summary>
        <div className="mt-4 max-h-80 space-y-2 overflow-y-auto pr-2">{proof.stopping_rules.hold_evidence.map((hold) => {
          const recoveryCase = casesById.get(hold.case_id);
          return <article key={hold.case_id} className="rounded-xl border border-emerald-300/10 bg-emerald-300/[.025] p-3"><div className="flex items-start justify-between gap-3"><div><p className="text-xs font-semibold text-white">{hold.customer_name}</p><p className="mt-1 text-[10px] text-slate-500">{hold.invoice_number ?? "Portfolio case"} · {hold.provenance}</p></div>{recoveryCase && <button type="button" onClick={() => onSelectCase(recoveryCase)} className="text-[11px] font-semibold text-sky-300">Open case →</button>}</div><p className="mt-2 text-[11px] text-emerald-200">Recovery intentionally withheld: {hold.reasons.map(label).join(" · ")}</p><p className="mt-1 text-[10px] text-slate-500">Current recommendation: {label(hold.current_recommendation)}</p></article>;
        })}{!proof.stopping_rules.hold_evidence.length && <p className="py-5 text-xs text-slate-500">No current stopping-rule holds exist in this batch.</p>}</div>
      </details>
    </div>
  </Panel>;
}

function ProofAmount({ label: amountLabel, value, detail, tone = "sky", money = true, meta }: { label: string; value: string; detail: string; tone?: "sky" | "emerald" | "rose"; money?: boolean; meta?: { unit: string; scope: string; window: string } }) {
  const colors = { sky: "text-sky-200", emerald: "text-emerald-200", rose: "text-rose-200" };
  return <article className="proof-amount interactive-card bg-[#08111f] p-5 sm:p-6"><p className="text-[10px] font-bold uppercase tracking-[.13em] text-slate-300">{amountLabel}</p><p className={`mt-2 text-2xl font-semibold tabular-nums tracking-[-.03em] sm:text-3xl ${colors[tone]}`}>{money ? formatMoney(value) : value}</p><p className="mt-1 text-[11px] leading-5 text-slate-400">{detail}</p>{meta && <p className="mt-2 text-[9px] uppercase leading-4 tracking-[.09em] text-slate-600">Unit {meta.unit} · scope {meta.scope} · {meta.window}</p>}</article>;
}

function BaselineValue({ value, label: baselineLabel }: { value: number; label: string }) {
  return <div><p className="text-xl font-semibold tabular-nums text-white">{value}</p><p className="mt-1 text-[10px] leading-4 text-slate-500">{baselineLabel}</p></div>;
}

function ExecutiveSnapshot({ recovery, intelligence, latestCycle, events, actions }: ReportProps) {
  const elevated = intelligence.level_counts.CRITICAL + intelligence.level_counts.HIGH;
  const recovered = events.filter((event) => event.cycle === latestCycle?.cycle).reduce((sum, event) => sum + Number(event.metadata.payment_amount ?? 0), 0);
  const awaiting = actions.filter((item) => item.status === "PENDING_APPROVAL").length;
  const executed = actions.filter((item) => item.status === "EXECUTED").length;
  return <Panel className="overflow-hidden"><SectionHeader eyebrow="Portfolio position" title="Executive Recovery Snapshot" detail={`Current persisted position evaluated across ${intelligence.customer_count} customer accounts.`} prominent /><div className="grid grid-cols-2 gap-px bg-white/[.06] md:grid-cols-3 xl:grid-cols-6"><ReportMetric label="Overdue exposure" value={formatMoney(recovery.overdue_exposure)} detail="INR · current overdue cohort" tone="rose" /><ReportMetric label="Elevated accounts" value={String(elevated)} detail={`${intelligence.level_counts.CRITICAL} critical · ${intelligence.level_counts.HIGH} high · customers`} tone="amber" /><ReportMetric label="Payments this cycle" value={recovered ? formatMoney(recovered) : "—"} detail="INR · current-cycle persisted events" tone="emerald" /><ReportMetric label="Current blocker cases" value={String(recovery.cases_blocked_by_dispute + recovery.cases_awaiting_payment)} detail={`${recovery.cases_blocked_by_dispute} disputes · ${recovery.cases_awaiting_payment} promises`} tone="sky" /><ReportMetric label="Workflow requests awaiting approval" value={String(awaiting)} detail="Persisted workflows · current status" tone="amber" /><ReportMetric label="Executed workflows" value={String(executed)} detail="Persisted internal workflow history" tone="emerald" /></div></Panel>;
}

function MaterialChanges({ latestCycle, events, casesByCustomer, casesById, onSelectCase }: ReportProps & { casesByCustomer: Map<string, PriorityCase>; casesById: Map<string, PriorityCase> }) {
  if (!latestCycle) return <Panel className="overflow-hidden"><SectionHeader eyebrow="Material changes" title="No simulation-cycle evidence recorded yet" detail="Current portfolio decisions remain available below; no before/after result is being inferred." prominent /></Panel>;
  const related = new Map<string, { id: string; type: string; family: string; role: string }>();
  for (const transition of latestCycle.transitions) for (const event of transition.related_events ?? []) related.set(event.id, event);
  const cycleEvents = related.size ? [...related.values()] : events.filter((event) => event.cycle === latestCycle.cycle).map((event) => ({ id: event.id, type: event.type, family: "", role: "" }));
  const paymentEvents = cycleEvents.filter((event) => event.type.includes("PAYMENT")).length;
  const promiseEvents = cycleEvents.filter((event) => event.type.includes("PROMISE") || event.type.includes("COMMITMENT")).length;
  const disputeEvents = cycleEvents.filter((event) => event.type.includes("DISPUTE")).length;
  const examples = [...latestCycle.transitions].filter((item) => item.entity_type === "CUSTOMER").sort((left, right) => Number(right.classifications.includes("RECOMMENDATION_CHANGED")) - Number(left.classifications.includes("RECOMMENDATION_CHANGED")) || Number(right.material) - Number(left.material)).slice(0, 4);
  return <Panel className="overflow-hidden"><SectionHeader eyebrow="Material changes" title={`What changed in cycle ${latestCycle.cycle}`} detail="Persisted events are separated from material decision movement." prominent /><div className="grid grid-cols-2 gap-px border-b border-white/[.06] bg-white/[.06] sm:grid-cols-4 xl:grid-cols-8"><ReportMetric label="Accounts reassessed" value={String(latestCycle.customers_affected)} detail="Received factual events" tone="sky" /><ReportMetric label="Decisions changed" value={String(latestCycle.recommendations_changed)} detail="Recommendation moved" tone="rose" /><ReportMetric label="Decisions held" value={String(latestCycle.recommendations_unchanged)} detail="Facts changed; decision held" tone="emerald" /><ReportMetric label="Blockers added" value={String(latestCycle.blockers_added)} detail="New supported constraint" tone="amber" /><ReportMetric label="Blockers removed" value={String(latestCycle.blockers_removed)} detail="Constraint resolved" tone="emerald" /><ReportMetric label="Payment events" value={String(paymentEvents)} detail="Received or applied" tone="emerald" /><ReportMetric label="Promise events" value={String(promiseEvents)} detail="Created or broken" tone="amber" /><ReportMetric label="Dispute events" value={String(disputeEvents)} detail="Opened or resolved" tone="sky" /></div><div className="divide-y divide-white/[.055]">{examples.map((transition) => {
    const recoveryCase = casesByCustomer.get(transition.entity_id) ?? casesById.get(transition.entity_id);
    const decisionChanged = transition.classifications.includes("RECOMMENDATION_CHANGED");
    return <article key={`${transition.entity_type}-${transition.entity_id}`} className={`interactive-row grid gap-5 border-l-[3px] p-5 sm:p-6 lg:grid-cols-[minmax(210px,.8fr)_minmax(320px,1.2fr)_minmax(300px,1.15fr)_auto] lg:items-center ${decisionChanged ? "border-l-rose-300/70 bg-rose-300/[.018]" : "border-l-emerald-300/55 bg-emerald-300/[.015]"}`}><div><div className="flex flex-wrap items-center gap-2"><h3 className="text-lg font-semibold text-white">{transition.entity_name}</h3><StatusPill tone={decisionChanged ? "rose" : "emerald"}>{decisionChanged ? "Decision changed" : "Decision held"}</StatusPill></div><p className="mt-2 text-xs font-medium text-slate-400">Current risk: {transition.current_risk_level} · Current Intelligence Score {transition.current_score}/100</p></div><div><p className="text-[10px] font-bold uppercase tracking-[.12em] text-slate-400">Decision movement</p><div className="mt-2 flex flex-wrap items-center gap-2 text-sm font-semibold"><span className="text-slate-500 line-through decoration-slate-500/50">{transition.previous_recommendation ? label(transition.previous_recommendation) : "Previously unavailable"}</span><span className="text-lg text-sky-300">→</span><span className="text-white">{transition.current_recommendation_title}</span></div><p className="mt-2 text-sm tabular-nums text-slate-400">Score <span className="text-slate-500">{transition.previous_score ?? "—"}</span> <span className="mx-1 text-sky-300">→</span> <strong className="text-lg text-white">{transition.current_score}</strong></p></div><div><p className="text-[13px] font-medium leading-6 text-slate-200">{transition.what_changed}</p><p className="mt-2 text-xs leading-5 text-slate-400">{transition.decision_impact}</p></div>{recoveryCase ? <button type="button" onClick={() => onSelectCase(recoveryCase)} className={buttonStyles.secondary}>Open evidence</button> : <span className="text-xs text-slate-500">Portfolio evidence only</span>}</article>;
  })}{!examples.length && <p className="p-8 text-center text-xs text-slate-500">Cycle events were recorded without customer-level transition evidence.</p>}</div></Panel>;
}

function DecisionReport({ intelligence, casesByCustomer, onSelectCase }: ReportProps & { casesByCustomer: Map<string, PriorityCase> }) {
  const groups = [
    { title: "Escalate", actions: ["ESCALATE"], tone: "rose" as const },
    { title: "Prioritize / follow up", actions: ["PRIORITIZE_RECOVERY", "FOLLOW_UP"], tone: "amber" as const },
    { title: "Review dispute", actions: ["REVIEW_DISPUTE"], tone: "sky" as const },
    { title: "Monitor promise", actions: ["WAIT_FOR_PROMISE"], tone: "emerald" as const },
    { title: "Routine monitoring", actions: ["MONITOR"], tone: "slate" as const },
  ].map((group) => ({ ...group, items: intelligence.customers.filter((item) => group.actions.includes(item.recommendation.action)).sort((left, right) => right.score - left.score) }));
  return <Panel className="overflow-hidden"><SectionHeader eyebrow="Priority decisions" title="Current deterministic recovery decisions" detail={`${intelligence.customer_count} mutually exclusive customer recommendations grouped by current recommended action.`} prominent /><div className="grid gap-px bg-white/[.06] md:grid-cols-2 xl:grid-cols-5">{groups.map((group) => {
    const example = group.items[0];
    const recoveryCase = example ? casesByCustomer.get(example.entity_id) : undefined;
    return <article key={group.title} className="flex min-h-64 flex-col bg-[#08111f] p-5"><div className="flex items-center justify-between gap-2"><StatusPill tone={group.tone}>{group.title}</StatusPill><span className="text-sm font-semibold tabular-nums text-slate-300"><strong className="text-2xl text-white">{group.items.length}</strong> accounts</span></div>{example ? <><p className="mt-5 text-base font-semibold text-white">{example.entity_name}</p><p className="mt-1 text-xs text-slate-400">Current risk: {example.level} · score {example.score}/100</p><p className="mt-3 line-clamp-3 text-[13px] leading-6 text-slate-200">{example.recommendation.explanation}</p><p className="mt-2 text-xs text-slate-400">Evidence: {example.signals[0]?.title ?? "Current receivables state"}</p>{recoveryCase && !recoveryCase.allowed && <p className="mt-2 rounded-lg border border-amber-300/15 bg-amber-300/[.04] px-2.5 py-2 text-xs text-amber-100/80">Blocker: {recoveryCase.reason}</p>}{recoveryCase && <button type="button" onClick={() => onSelectCase(recoveryCase)} className="mt-auto pt-5 text-left text-xs font-semibold text-sky-300">Open representative case →</button>}</> : <p className="mt-6 text-xs text-slate-500">No current decisions in this group.</p>}</article>;
  })}</div></Panel>;
}

function DeliberateRestraint({ intelligence, casesByCustomer, onSelectCase }: ReportProps & { casesByCustomer: Map<string, PriorityCase> }) {
  const holds = intelligence.customers.filter((item) => item.recommendation.action === "MONITOR" || item.recommendation.action === "WAIT_FOR_PROMISE").sort((left, right) => Number(right.metrics.overdue_exposure) - Number(left.metrics.overdue_exposure)).slice(0, 4);
  return <Panel className="overflow-hidden border-emerald-300/15"><SectionHeader eyebrow="Deliberate holds" title="Where ReconMate is intentionally not escalating" detail="Overdue does not automatically mean more customer contact." prominent /><div className="grid gap-px bg-white/[.06] md:grid-cols-2">{holds.map((item) => {
    const recoveryCase = casesByCustomer.get(item.entity_id);
    const evidence = [item.metrics.active_promise_count ? "Active promise remains valid" : null, item.metrics.active_dispute_count ? "Active dispute blocks recovery" : null, item.metrics.days_since_last_payment !== null && item.metrics.days_since_last_payment < 30 ? `Payment recorded ${item.metrics.days_since_last_payment} days ago` : null].filter((value): value is string => Boolean(value));
    return <article key={item.entity_id} className="border-l-[3px] border-l-emerald-300/45 bg-[#08111f] p-5 sm:p-6"><p className="mb-4 text-xs font-extrabold uppercase tracking-[.16em] text-emerald-200">Do not act yet</p><div className="flex items-start justify-between gap-3"><div><h3 className="text-base font-semibold text-white">{item.entity_name}</h3><p className="mt-1 text-[13px] text-slate-400">{formatMoney(item.metrics.overdue_exposure)} overdue · {item.metrics.max_days_overdue} days maximum</p></div><StatusPill tone="emerald">{item.recommendation.title}</StatusPill></div><p className="mt-4 text-[13px] leading-6 text-slate-200">{item.recommendation.explanation}</p><div className="mt-3 flex flex-wrap gap-2">{(evidence.length ? evidence : [item.signals[0]?.title ?? "Current behaviour remains inside monitoring policy"]).map((value) => <span key={value} className="rounded-full border border-emerald-300/15 bg-emerald-300/[.04] px-3 py-1.5 text-xs text-emerald-100/80">{value}</span>)}</div>{recoveryCase && <button type="button" onClick={() => onSelectCase(recoveryCase)} className="mt-5 text-xs font-semibold text-sky-300">Review hold evidence →</button>}</article>;
  })}{!holds.length && <p className="bg-[#08111f] p-8 text-center text-xs text-slate-500 md:col-span-2">No current monitor or wait decisions are recorded.</p>}</div></Panel>;
}

const workflowStatuses = ["PENDING_APPROVAL", "APPROVED", "REJECTED", "HELD", "CANCELLED", "EXECUTED"] as const;
type ActivityFilter = (typeof workflowStatuses)[number] | "EXTERNAL_REQUESTS" | null;

function OperatorActivity({ actions, paymentRequests, casesById, onSelectCase }: ReportProps & { casesById: Map<string, PriorityCase> }) {
  const [filter, setFilter] = useState<ActivityFilter>(null);
  const counts = new Map<string, number>();
  for (const item of actions) counts.set(item.status, (counts.get(item.status) ?? 0) + 1);
  const visibleActions = filter === "EXTERNAL_REQUESTS" ? [] : actions.filter((item) => filter === null || item.status === filter);
  const recent = [...visibleActions].sort((left, right) => new Date(right.created_at ?? 0).getTime() - new Date(left.created_at ?? 0).getTime()).slice(0, 8);
  const visibleRequests = filter === null || filter === "EXTERNAL_REQUESTS" ? paymentRequests.slice(0, 5) : [];
  const selectFilter = (next: Exclude<ActivityFilter, null>) => setFilter((current) => current === next ? null : next);
  const categoryClass = (active: boolean, external = false) => `rounded-lg border px-2.5 py-1.5 text-[10px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300/60 ${active ? external ? "border-violet-200/45 bg-violet-300/[.14] text-violet-100" : "border-sky-200/40 bg-sky-300/[.12] text-sky-100" : external ? "border-violet-300/15 bg-violet-300/[.04] text-violet-200 hover:border-violet-200/35" : "border-white/[.07] bg-white/[.025] text-slate-400 hover:border-sky-200/25 hover:text-slate-200"}`;

  return <Panel className="overflow-hidden">
    <SectionHeader eyebrow="Operator actions" title="Workflow outcomes" detail="Select a category to filter persisted workflows and external provider requests." prominent />
    <div className="flex flex-wrap gap-2 border-b border-white/[.06] px-5 py-3" aria-label="Filter workflow outcomes">
      <button type="button" aria-pressed={filter === null} onClick={() => setFilter(null)} className={categoryClass(filter === null)}><strong className="mr-1 text-white">{actions.length + paymentRequests.length}</strong>ALL</button>
      {workflowStatuses.map((status) => <button type="button" key={status} aria-pressed={filter === status} onClick={() => selectFilter(status)} className={categoryClass(filter === status)}><strong className="mr-1 text-white">{counts.get(status) ?? 0}</strong>{label(status)}</button>)}
      <button type="button" aria-pressed={filter === "EXTERNAL_REQUESTS"} onClick={() => selectFilter("EXTERNAL_REQUESTS")} className={categoryClass(filter === "EXTERNAL_REQUESTS", true)}><strong className="mr-1 text-white">{paymentRequests.length}</strong>external requests</button>
    </div>
    {visibleRequests.length > 0 && <div className="divide-y divide-white/[.055] border-b border-white/[.06]">{visibleRequests.map((request) => {
      const recoveryCase = casesById.get(request.case_id);
      return <article key={request.id} className="interactive-row grid gap-3 border-l-[3px] border-l-violet-300/45 p-5 lg:grid-cols-[minmax(190px,.8fr)_minmax(260px,1fr)_140px_minmax(190px,.8fr)_auto] lg:items-center"><div><p className="text-base font-semibold text-white">{recoveryCase?.customerName ?? `Case ${request.case_id.slice(0, 8)}`}</p><p className="mt-1 text-xs text-violet-200">Source: {request.provider_mode === "TEST" ? "Razorpay Test Mode" : "Provider Demo Mode"}</p></div><div><p className="text-[13px] font-semibold text-sky-200">Payment request · {formatMoney(request.requested_amount)}</p><p className="mt-1 text-xs text-slate-400">Request {request.provider_reference ?? "not issued"}{Number(request.paid_amount) ? ` · ${formatMoney(request.paid_amount)} payment persisted` : " · financial mutation: none"}</p></div><StatusPill tone={request.status === "FAILED" ? "rose" : request.status === "PAID" ? "emerald" : "sky"}>{label(request.status)}</StatusPill><div><p className="text-xs text-slate-300">{request.operator_id}</p><p className="mt-1 text-[11px] text-slate-500">{labeledTimestamp(request.created_at, "recorded")}</p></div>{recoveryCase && <button type="button" onClick={() => onSelectCase(recoveryCase)} className={buttonStyles.secondary}>Open evidence</button>}</article>;
    })}</div>}
    <div className="divide-y divide-white/[.055]">{recent.map((action) => {
      const recoveryCase = casesById.get(action.case_id);
      const timestamp = action.executed_at ?? action.decision_at ?? action.created_at;
      return <article key={action.id} className="interactive-row grid gap-3 p-5 lg:grid-cols-[minmax(190px,.8fr)_minmax(240px,1fr)_140px_minmax(190px,.8fr)_auto] lg:items-center"><div><p className="text-base font-semibold text-white">{recoveryCase?.customerName ?? `Case ${action.case_id.slice(0, 8)}`}</p><p className="mt-1 text-xs text-slate-500">Internal workflow record</p></div><div><p className="text-[13px] font-semibold text-sky-200">{label(action.recommended_action ?? action.action_type)}</p><p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-400">{action.decision_reason ?? action.reason ?? action.recommendation_context?.workflow_effect ?? "No additional operator reason recorded."}</p></div><StatusPill tone={action.status === "EXECUTED" ? "emerald" : action.status === "PENDING_APPROVAL" ? "amber" : action.status === "REJECTED" || action.status === "CANCELLED" ? "rose" : "sky"}>{label(action.status)}</StatusPill><div><p className="text-xs text-slate-300">{action.executed_by ?? action.decision_by ?? "System-created record"}</p><p className="mt-1 text-[11px] text-slate-500">{labeledTimestamp(timestamp, "recorded")}</p></div>{recoveryCase && <button type="button" onClick={() => onSelectCase(recoveryCase)} className={buttonStyles.secondary}>Open case</button>}</article>;
    })}{!recent.length && !visibleRequests.length && <p className="p-8 text-center text-xs text-slate-500">No workflow outcomes exist in this category.</p>}</div>
  </Panel>;
}

function OutstandingExceptions({ queue, actions, intelligenceByCustomer, casesById, onSelectCase }: ReportProps & { intelligenceByCustomer: Map<string, IntelligenceResult>; casesById: Map<string, PriorityCase> }) {
  const actionsByCase = new Map<string, RecoveryAction[]>();
  for (const action of actions) actionsByCase.set(action.case_id, [...(actionsByCase.get(action.case_id) ?? []), action]);
  const criticalWithoutExecution = queue.filter((item) => intelligenceByCustomer.get(item.customerId)?.level === "CRITICAL" && item.state !== "RESOLVED" && !(actionsByCase.get(item.id) ?? []).some((action) => action.status === "EXECUTED"));
  const unresolvedPromises = queue.filter((item) => intelligenceByCustomer.get(item.customerId)?.metrics.broken_promise_count && item.state !== "RESOLVED");
  const disputeBlocked = queue.filter((item) => intelligenceByCustomer.get(item.customerId)?.metrics.active_dispute_count && item.state !== "RESOLVED");
  const pending = queue.filter((item) => (actionsByCase.get(item.id) ?? []).some((action) => action.status === "PENDING_APPROVAL"));
  const exceptions = [{ title: "Critical without completed action", items: criticalWithoutExecution, tone: "rose" as const }, { title: "Unresolved broken promises", items: unresolvedPromises, tone: "amber" as const }, { title: "Disputes blocking recovery", items: disputeBlocked, tone: "sky" as const }, { title: "Workflow requests awaiting approval", items: pending, tone: "amber" as const }];
  return <Panel className="overflow-hidden"><SectionHeader eyebrow="Outstanding exceptions" title="What remains unresolved" detail="Current supported conditions requiring follow-through or continued monitoring." prominent /><div className="grid gap-px bg-white/[.06] sm:grid-cols-2 xl:grid-cols-4">{exceptions.map((exception) => {
    const example = exception.items[0];
    return <article key={exception.title} className="bg-[#08111f] p-4"><div className="flex items-center justify-between gap-2"><StatusPill tone={exception.tone}>{exception.title}</StatusPill><span className="text-2xl font-semibold tabular-nums text-white">{exception.items.length}</span></div>{example ? <><p className="mt-4 text-sm font-semibold text-white">{example.customerName}</p><p className="mt-1 text-[10px] text-slate-500">{example.amount} · {example.daysOverdue} days overdue</p><button type="button" onClick={() => onSelectCase(casesById.get(example.id) ?? example)} className="mt-4 text-xs font-semibold text-sky-300">Inspect exception →</button></> : <p className="mt-5 text-xs text-slate-600">No current exception in this category.</p>}</article>;
  })}</div></Panel>;
}

function ReportMetric({ label: metricLabel, value, detail, tone }: { label: string; value: string; detail: string; tone: "rose" | "amber" | "sky" | "emerald" }) {
  const colors = { rose: "text-rose-200", amber: "text-amber-100", sky: "text-sky-200", emerald: "text-emerald-200" };
  return <article className="bg-[#08111f] p-5"><p className="text-[10px] font-bold uppercase leading-4 tracking-[.12em] text-slate-400">{metricLabel}</p><p className={`mt-2 text-2xl font-semibold tabular-nums tracking-[-.03em] ${colors[tone]}`}>{value}</p><p className="mt-1 text-xs leading-5 text-slate-500">{detail}</p></article>;
}
