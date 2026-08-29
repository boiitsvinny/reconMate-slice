"use client";

import { useEffect, useMemo, useState } from "react";
import type { Customer, PriorityCase } from "@/components/dashboard/data";
import { formatMoney } from "@/components/dashboard/data";
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

type CommandResultViewProps = {
  command: string;
  result: CommandResult;
  customer?: Customer;
  customerCases?: PriorityCase[];
  onOpenTarget?: (targetType: string, targetId: string) => boolean;
  onOpenWorkspace?: (customerId: string) => boolean;
  onTryCommand?: (command: string) => void;
};

export function CommandResultView({ command, result, customer, customerCases = [], onOpenTarget, onOpenWorkspace, onTryCommand }: CommandResultViewProps) {
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
  const reminderPlan = result.interpreted_intent.intent === "PREPARE_PAYMENT_REMINDERS";
  const directQuery = result.interpreted_intent.query.entity === "INVOICES" || result.interpreted_intent.query.entity === "PAYMENTS";
  const nonSendableProposals = reminderPlan
    ? result.plan.proposed_actions.filter((proposal) => proposal.reminder_artifact?.status !== "PREPARED_FOR_REVIEW")
    : [];
  const preparedProposals = reminderPlan
    ? result.plan.proposed_actions.filter((proposal) => proposal.reminder_artifact?.status === "PREPARED_FOR_REVIEW")
    : result.plan.proposed_actions;
  const selectedCount = selected.size;
  const openTarget = (targetType: string, targetId: string) => {
    const opened = onOpenTarget?.(targetType, targetId) ?? false;
    setTargetNotice(opened ? null : "This result has no active recovery case workspace. Its current intelligence remains available below.");
  };
  if (isUnknown) {
    const suggestions = ["Who should I focus on today?", "Show overdue invoices above 2 lakh", "Payments received this cycle", "Compare Mintleaf and Prime"];
    return (
      <Panel className="mt-6 border-amber-300/15">
        <SectionHeader eyebrow="Unsupported request" title="ReconMate cannot answer this from the current receivables model." detail={result.interpreted_intent.guidance ?? result.understanding_summary} prominent />
        <div className="space-y-4 p-5"><div><p className="text-[10px] font-bold uppercase tracking-[.12em] text-slate-500">Your request</p><p className="mt-1.5 text-sm leading-6 text-slate-200">“{command}”</p></div><AnalysisList title="Supported analysis dimensions" items={["Overdue exposure and invoice age", "Payments and payment activity", "Promises and broken commitments", "Disputes and action blockers", "Current risk and recovery state", "Latest operational changes"]} empty="" />{onTryCommand && <div><p className="text-[10px] font-bold uppercase tracking-[.12em] text-slate-500">Try a supported investigation</p><div className="mt-2 flex flex-wrap gap-2">{suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => onTryCommand(suggestion)} className="rounded-full border border-white/[.08] bg-white/[.025] px-3 py-1.5 text-left text-[11px] text-slate-300 hover:border-sky-300/25 hover:text-sky-100">{suggestion}</button>)}</div></div>}</div>
      </Panel>
    );
  }

  return (
    <div className="mt-6 space-y-6" aria-live="polite">
      <CommandAnswer command={command} result={result} />
      {result.interpreted_intent.intent === "CUSTOMER_ANALYSIS" && customer && result.analyzed_entities[0]?.entity_id === customer.id && (
        <CustomerOperationalBrief customer={customer} cases={customerCases} entity={result.analyzed_entities[0]} result={result} onOpenWorkspace={onOpenWorkspace} />
      )}
      <section className="grid gap-4 lg:grid-cols-[minmax(0,1.08fr)_minmax(340px,.92fr)]">
        <InterpretationPanel result={result} />
        <InspectionPanel result={result} />
      </section>

      {result.direct_records.length > 0 && <DirectRecordsPanel result={result} />}
      {!directQuery && result.result_kind !== "COMPARE" && <RankedEvidencePanel result={result} onOpenTarget={onOpenTarget ? openTarget : undefined} />}
      {directQuery && result.direct_records.length === 0 && result.result_kind !== "COUNT" && <Panel className="overflow-hidden"><SectionHeader eyebrow="Query outcome" title="No persisted records matched" detail={`${result.query_evidence.records_inspected} records were inspected and every structured condition was applied.`} prominent /></Panel>}

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
        <SectionHeader eyebrow="Prepared command output" title={reminderPlan ? `${preparedProposals.length} sendable reminder draft${preparedProposals.length === 1 ? "" : "s"}` : `Bounded work plan · ${result.plan.proposed_actions.length} proposal${result.plan.proposed_actions.length === 1 ? "" : "s"}`} detail={reminderPlan ? `${nonSendableProposals.length} account${nonSendableProposals.length === 1 ? "" : "s"} separated below because current case-level policy does not permit a reminder.` : result.plan.proposed_actions.length > 4 ? "Ordered results are bounded inside this panel; scroll to review every proposal." : `Plan ${result.plan.plan_id.slice(0, 8)} / ${label(result.plan.execution_mode)}`} prominent action={confirmationIds.length > 0 && !reviewing ? <button type="button" onClick={() => setReviewing(true)} className={buttonStyles.warning}>Review {confirmationIds.length} action{confirmationIds.length === 1 ? "" : "s"}</button> : undefined} />
        {!result.plan.proposed_actions.length ? (
          <div className="p-10 text-center"><p className="text-sm font-medium text-slate-300">No matching action proposals</p><p className="mt-2 text-xs text-slate-500">No current record matched the interpreted command filters.</p></div>
        ) : (
          <div className="operational-scrollbar max-h-[42rem] overflow-y-auto overscroll-contain p-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-sky-300/35 lg:p-5" role="region" aria-label={`${result.plan.proposed_actions.length} operational proposals`} tabIndex={0}>
            {preparedProposals.length > 0 && <div className="grid gap-4 lg:grid-cols-2">
              {preparedProposals.map((proposal) => (
                <ActionProposalCard key={proposal.proposal_id} proposal={proposal} outcome={outcomes.get(proposal.proposal_id)} targetName={entityNames.get(proposal.target_id)} selected={selected.has(proposal.proposal_id)} onSelectedChange={reviewing && proposal.requires_confirmation ? (checked) => setSelected((current) => {
                  const next = new Set(current);
                  if (checked) next.add(proposal.proposal_id); else next.delete(proposal.proposal_id);
                  return next;
                }) : undefined} onOpenTarget={onOpenTarget && (proposal.target_type === "CUSTOMER" || proposal.target_type === "RECOVERY_CASE" || proposal.target_type === "CASE") ? () => {
                  const opened = onOpenTarget(proposal.target_type, proposal.target_id);
                  setTargetNotice(opened ? null : "This result has no active recovery case workspace. Its current intelligence remains available below.");
                } : undefined} />
              ))}
            </div>}
            {reminderPlan && nonSendableProposals.length > 0 && <section className={preparedProposals.length ? "mt-6 border-t border-white/[.07] pt-5" : ""}>
              <p className="text-[10px] font-bold uppercase tracking-[.14em] text-amber-200">Non-sendable accounts</p>
              <p className="mt-1 text-xs leading-5 text-slate-400">Shown for policy transparency only. These are not payment-reminder matches and no usable draft was prepared.</p>
              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                {nonSendableProposals.map((proposal) => <ActionProposalCard key={proposal.proposal_id} proposal={proposal} outcome={outcomes.get(proposal.proposal_id)} targetName={entityNames.get(proposal.target_id)} onOpenTarget={onOpenTarget && proposal.target_type === "CUSTOMER" ? () => {
                  const opened = onOpenTarget(proposal.target_type, proposal.target_id);
                  setTargetNotice(opened ? null : "This result has no active recovery case workspace. Its current intelligence remains available below.");
                } : undefined} />)}
              </div>
            </section>}
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

    </div>
  );
}

function CommandAnswer({ command, result }: { command: string; result: CommandResult }) {
  const count = result.query_evidence.records_matched;
  const entity = result.analyzed_entities[0];
  const answer = result.result_kind === "COUNT"
    ? `${count} matching ${result.interpreted_intent.query.entity.toLowerCase().replaceAll("_", " ")}`
    : result.result_kind === "COMPARE"
      ? result.analyzed_entities.length === 2 ? `${result.analyzed_entities[0].entity_name} compared with ${result.analyzed_entities[1].entity_name}` : "Two unambiguous customer records were not resolved"
      : result.result_kind === "EXACT_ENTITY" && result.direct_records[0]
        ? result.direct_records[0].display_name
        : result.result_kind === "EXACT_ENTITY" && entity
          ? `${entity.entity_name} · ${entity.recommendation.title}`
          : result.result_kind === "INVOICES" || result.result_kind === "PAYMENTS"
            ? `${count} matching persisted ${result.result_kind.toLowerCase()}`
            : result.understanding_summary;
  return <Panel className="overflow-hidden border-sky-300/20">
    <div className="grid gap-px bg-white/[.06] lg:grid-cols-[.85fr_1.1fr_1.35fr]">
      <AnswerCell label="What you asked" value={`“${command}”`} />
      <AnswerCell label="What ReconMate understood" value={objectives[result.interpreted_intent.intent]} />
      <AnswerCell label="Answer" value={answer} primary />
    </div>
  </Panel>;
}

function AnswerCell({ label: answerLabel, value, primary = false }: { label: string; value: string; primary?: boolean }) {
  return <div className={primary ? "bg-sky-300/[.045] p-4 sm:p-5" : "bg-[#08111f]/90 p-4 sm:p-5"}><p className="text-[10px] font-bold uppercase tracking-[.13em] text-slate-500">{answerLabel}</p><p className={`mt-2 leading-6 ${primary ? "text-base font-semibold text-white" : "text-sm text-slate-300"}`}>{value}</p></div>;
}

function DirectRecordsPanel({ result }: { result: CommandResult }) {
  const payments = result.interpreted_intent.query.entity === "PAYMENTS";
  const [sort, setSort] = useState<{ field: "invoice" | "age"; direction: "asc" | "desc" } | null>(null);
  const records = [...result.direct_records].sort((left, right) => {
    if (payments || !sort) return 0;
    const comparison = sort.field === "invoice"
      ? (left.invoice_number ?? left.display_name).localeCompare(right.invoice_number ?? right.display_name, undefined, { numeric: true })
      : (left.days_overdue ?? 0) - (right.days_overdue ?? 0);
    return sort.direction === "asc" ? comparison : -comparison;
  });
  const toggleSort = (field: "invoice" | "age") => setSort((current) => current?.field === field
    ? { field, direction: current.direction === "asc" ? "desc" : "asc" }
    : { field, direction: field === "age" ? "desc" : "asc" });
  const sortIndicator = (field: "invoice" | "age") => sort?.field === field ? (sort.direction === "asc" ? " ↑" : " ↓") : "";
  return <Panel className="overflow-hidden">
    <SectionHeader eyebrow="Persisted factual records" title={payments ? "Payment records" : "Invoice records"} detail={`${result.query_evidence.records_returned} of ${result.query_evidence.records_matched} matching records shown`} prominent />
    <div className="operational-scrollbar max-h-72 overflow-x-hidden overflow-y-auto overscroll-contain" role="region" aria-label={payments ? "Matching payments" : "Matching invoices"} tabIndex={0}>
      <table className="w-full table-fixed border-collapse text-left text-xs">
        <thead className="sticky top-0 z-10 bg-[#08111f]"><tr className="border-b border-white/[.07] text-[10px] uppercase tracking-[.12em] text-slate-500"><th aria-sort={!payments && sort?.field === "invoice" ? (sort.direction === "asc" ? "ascending" : "descending") : "none"} className="w-[13%] px-3 py-3 sm:px-5">{payments ? "Payment" : <button type="button" onClick={() => toggleSort("invoice")} className="font-semibold hover:text-sky-200 focus-visible:outline-none focus-visible:text-sky-200">Invoice{sortIndicator("invoice")}</button>}</th><th className="w-[24%] px-3 py-3 sm:px-5">Customer</th><th className="w-[15%] px-3 py-3 sm:px-5">{payments ? "Invoice" : "Original amount"}</th><th className="w-[15%] px-3 py-3 sm:px-5">{payments ? "Amount" : "Outstanding"}</th><th aria-sort={!payments && sort?.field === "age" ? (sort.direction === "asc" ? "ascending" : "descending") : "none"} className="w-[20%] px-3 py-3 sm:px-5">{payments ? "Payment date" : <button type="button" onClick={() => toggleSort("age")} className="font-semibold hover:text-sky-200 focus-visible:outline-none focus-visible:text-sky-200">Due / age{sortIndicator("age")}</button>}</th><th className="w-[13%] px-3 py-3 sm:px-5">Status</th></tr></thead>
        <tbody className="divide-y divide-white/[.055]">{records.map((record) => <tr key={record.entity_id} className="interactive-row"><td className="break-words px-3 py-4 font-semibold text-sky-100 sm:px-5">{record.display_name}</td><td className="break-words px-3 py-4 text-slate-200 sm:px-5">{record.customer_name}</td><td className="break-words px-3 py-4 tabular-nums text-slate-300 sm:px-5">{payments ? record.invoice_number : formatMoney(record.original_amount ?? "0")}</td><td className="break-words px-3 py-4 font-semibold tabular-nums text-white sm:px-5">{formatMoney(record.amount ?? record.outstanding_amount ?? "0")}</td><td className="break-words px-3 py-4 text-slate-300 sm:px-5">{payments ? record.payment_date : `${record.due_date ?? "—"} · ${record.days_overdue ?? 0}d overdue`}</td><td className="px-3 py-4 sm:px-5"><StatusPill tone={record.status === "PAID" ? "emerald" : record.status === "DISPUTED" ? "amber" : "slate"}>{record.status ?? "Persisted"}</StatusPill></td></tr>)}</tbody>
      </table>
    </div>
  </Panel>;
}

function CustomerOperationalBrief({ customer, cases, entity, result, onOpenWorkspace }: { customer: Customer; cases: PriorityCase[]; entity: CommandResult["analyzed_entities"][number]; result: CommandResult; onOpenWorkspace?: (customerId: string) => boolean }) {
  const caseBlocker = cases.find((item) => !item.allowed)?.reason;
  const blocker = caseBlocker ?? (entity.metrics.active_dispute_count
    ? "Active dispute requires review"
    : entity.metrics.active_promise_count
      ? "Valid payment promise is active"
      : null);
  const workflowStates = [...new Set(cases.map((item) => label(item.state)))];
  const approvalRequired = cases.some((item) => item.humanApprovalRequired);
  const recentEvidence = result.query_evidence.latest_cycle?.observations.slice(0, 2) ?? [];
  return <Panel className="overflow-hidden border-sky-300/20">
    <SectionHeader eyebrow="Matched customer account" title={customer.name} detail={`${customer.account_reference} · Deterministic lookup against current customer records`} prominent action={onOpenWorkspace && cases.length ? <button type="button" onClick={() => onOpenWorkspace(customer.id)} className={buttonStyles.primary}>Preview recovery case</button> : undefined} />
    <div className="grid gap-px bg-white/[.06] sm:grid-cols-2 xl:grid-cols-4">
      <SemanticSummary label="Total exposure" value={formatMoney(entity.metrics.total_outstanding_amount)} detail="Current outstanding receivables" />
      <SemanticSummary label="Overdue exposure" value={formatMoney(entity.metrics.overdue_exposure)} detail={`${entity.metrics.overdue_invoice_count} overdue invoice(s)`} />
      <SemanticSummary label="Open recovery cases" value={String(entity.metrics.active_recovery_case_count)} detail={workflowStates.length ? workflowStates.join(" · ") : "No active case workspace"} />
      <SemanticSummary label="Policy risk score" value={`${entity.score}/100 · ${entity.level}`} detail="Deterministic current-state evaluation" />
    </div>
    <div className="grid gap-5 p-5 lg:grid-cols-2 xl:grid-cols-4">
      <AnalysisList title="What is happening?" items={[entity.recommendation.title, `${entity.metrics.active_promise_count} active / ${entity.metrics.broken_promise_count} broken promise(s)`, `${entity.metrics.active_dispute_count} active dispute(s)`]} empty="" />
      <AnalysisList title="Why?" items={[blocker ?? "No current stopping-rule blocker detected", ...entity.signals.slice(0, 2).map((signal) => signal.explanation)]} empty="No material signal is currently present." />
      <AnalysisList title="What changed?" items={recentEvidence} empty="No scoped material change is recorded in the latest cycle." />
      <AnalysisList title="What should happen next?" items={[entity.recommendation.explanation, approvalRequired ? "Human approval is required before material workflow action." : "No approval requirement is recorded on the open case.", cases.length ? `Workflow status: ${workflowStates.join(" · ")}.` : "No open Case Workspace is available for this account."]} empty="" />
    </div>
    <p className="border-t border-white/[.06] px-5 py-3 text-[11px] leading-5 text-slate-500">Communication interpretation may propose candidate evidence. This recovery recommendation and score are produced by deterministic policy; operators control confirmation and approval.</p>
  </Panel>;
}

function SemanticSummary({ label: fieldLabel, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="bg-[#08111f]/80 p-4"><p className="text-[10px] font-bold uppercase tracking-[.12em] text-slate-400">{fieldLabel}</p><p className="mt-2 text-lg font-semibold text-white">{value}</p><p className="mt-1 text-xs leading-5 text-slate-500">{detail}</p></div>;
}

function InterpretationPanel({ result }: { result: CommandResult }) {
  const query = result.interpreted_intent.query;
  const conditions = queryConditions(result);
  const exclusions = queryExclusions(result);
  const returnedLimit = result.query_evidence.records_matched > result.query_evidence.records_returned ? String(result.query_evidence.records_returned) : "All matches";
  const entityLabel = query.entity === "RECOVERY_CASES" ? "Recovery cases" : query.entity === "INVOICES" ? "Invoices" : query.entity === "PAYMENTS" ? "Payments" : "Customers";
  return <Panel className="overflow-hidden"><SectionHeader eyebrow="Structured scope" title="Filters and execution boundary" detail="Deterministic query details behind the answer above" prominent /><div className="p-5"><dl className="grid gap-x-5 gap-y-3 text-xs sm:grid-cols-2"><QueryRow term="Looking for" value={entityLabel} /><QueryRow term="Conditions" value={conditions.join(" + ") || "Current portfolio state"} /><QueryRow term="Excluded" value={exclusions.join(" + ") || "No explicit exclusions"} /><QueryRow term="Order" value={queryOrder(result)} /><QueryRow term="Limit" value={query.count_only ? "Count only" : query.limit ? String(query.limit) : returnedLimit} /><QueryRow term="Scope" value={query.time_scope === "LATEST_CYCLE" ? "Latest simulation cycle" : "Current portfolio"} /></dl></div></Panel>;
}

function InspectionPanel({ result }: { result: CommandResult }) {
  const evidence = result.query_evidence;
  const scope = evidence.inspection_scope;
  const scopeItems = [[scope.customers, "customers"], [scope.invoices, "invoices"], [scope.payments, "payments"], [scope.promises, "promises"], [scope.active_disputes, "active disputes"], [scope.recovery_cases, "recovery cases"], [scope.latest_cycle_events, "latest-cycle events"]] as const;
  const query = result.interpreted_intent.query;
  const relevantNames = new Set<string>([query.entity === "PAYMENTS" ? "payments" : query.entity === "INVOICES" ? "invoices" : "customers"]);
  if (query.entity === "RECOVERY_CASES") relevantNames.add("recovery cases");
  if (query.broken_promise || query.active_promise) relevantNames.add("promises");
  if (query.active_dispute !== null) relevantNames.add("active disputes");
  if (query.time_scope === "LATEST_CYCLE") relevantNames.add("latest-cycle events");
  if (relevantNames.size === 1) { relevantNames.add("invoices"); relevantNames.add("recovery cases"); }
  const compactScope = scopeItems.filter(([count, name]) => count > 0 && relevantNames.has(name)).map(([count, name]) => `${count} ${name}`).join(" · ");
  const scopeSummary = compactScope || (evidence.records_inspected > 0 ? `${evidence.records_inspected} operational records inspected` : "No operational records were available to inspect.");
  return <Panel className="overflow-hidden"><SectionHeader eyebrow="Grounded execution" title="What ReconMate inspected" detail={result.interpreted_intent.reasoning[0]} prominent /><div className="space-y-4 p-5"><div className="grid grid-cols-2 gap-3"><Metric label="Records inspected" value={String(evidence.records_inspected)} /><Metric label="Matched" value={String(evidence.records_matched)} /><Metric label="Excluded" value={String(evidence.records_excluded)} /><Metric label={query.count_only ? "Count result" : "Returned"} value={String(query.count_only ? evidence.records_matched : evidence.records_returned)} /></div><div><p className="text-[11px] font-bold uppercase tracking-[.12em] text-slate-400">Operational scope</p><p className="mt-2 text-[13px] leading-5 text-slate-200">{scopeSummary}</p>{scopeItems.some(([count]) => count > 0) && <details className="mt-3 rounded-xl border border-white/[.07] bg-white/[.02] p-3"><summary className="cursor-pointer text-xs font-semibold text-slate-400">View full inspected scope</summary><ul className="mt-3 grid gap-2 text-xs text-slate-300 sm:grid-cols-2">{scopeItems.filter(([count]) => count > 0).map(([count, name]) => <li key={name}>{count} {name}</li>)}</ul></details>}</div><AnalysisList title="Filtered from the inspected set" items={evidence.exclusions.map((item) => `${item.count} excluded: ${item.reason}`)} empty="No records were excluded by the applied conditions." /></div></Panel>;
}

function LatestCyclePanel({ result }: { result: CommandResult }) {
  const cycle = result.query_evidence.latest_cycle!;
  return <Panel className="overflow-hidden border-cyan-300/15"><SectionHeader eyebrow="Scoped latest-cycle evidence" title="What changed for these returned records" detail={`Cycle ${cycle.cycle} · ${cycle.event_count} provably associated event${cycle.event_count === 1 ? "" : "s"} across ${cycle.customers_affected} returned customer${cycle.customers_affected === 1 ? "" : "s"}`} prominent /><div className="grid gap-4 p-5 lg:grid-cols-[minmax(0,.72fr)_minmax(0,1.28fr)]"><div className="grid grid-cols-2 gap-3"><Metric label="Material changes" value={String(cycle.material_customers)} /><Metric label="Decisions changed" value={String(cycle.recommendations_changed)} /><Metric label="Decisions held" value={String(cycle.recommendations_unchanged)} /><Metric label="Events associated" value={String(cycle.event_count)} /></div><AnalysisList title="Factual before/after observations" items={cycle.observations} empty="Associated events were found without a material decision transition." /></div></Panel>;
}

function RankedEvidencePanel({ result, onOpenTarget }: { result: CommandResult; onOpenTarget?: (targetType: string, targetId: string) => void }) {
  const evidence = result.query_evidence;
  const reminderPlan = result.interpreted_intent.intent === "PREPARE_PAYMENT_REMINDERS";
  const names = new Map(result.analyzed_entities.map((entity) => [entity.entity_id, entity.entity_name]));
  if (!evidence.ranking.length) return <Panel className="overflow-hidden"><SectionHeader eyebrow="Query outcome" title={reminderPlan ? "No accounts are currently eligible for a payment reminder" : evidence.records_matched === 0 ? "No records matched the structured query" : `${evidence.records_matched} matching record${evidence.records_matched === 1 ? "" : "s"} counted`} detail={reminderPlan ? `ReconMate inspected ${evidence.records_inspected} overdue account${evidence.records_inspected === 1 ? "" : "s"}; non-sendable reasons remain visible in the prepared-output panel.` : evidence.records_matched === 0 ? `ReconMate inspected ${evidence.records_inspected} records and applied every condition shown above.` : "This count comes from current operational records; no ranked rows were requested."} prominent /></Panel>;
  return <Panel className="overflow-hidden"><SectionHeader eyebrow={reminderPlan ? "Eligible reminder cohort" : "What matched"} title={reminderPlan ? "Accounts permitted for reminder preparation" : "Returned records and ranking evidence"} detail={reminderPlan ? `${evidence.records_returned} account${evidence.records_returned === 1 ? "" : "s"} passed current case-level reminder policy.` : `${evidence.records_returned} of ${evidence.records_matched} matching record${evidence.records_matched === 1 ? "" : "s"} returned in the structured query order`} prominent /><div className="operational-scrollbar max-h-[46rem] divide-y divide-white/[.06] overflow-y-auto overscroll-contain" role="region" aria-label="Returned ranking evidence" tabIndex={0}>{evidence.ranking.map((item) => <article key={item.entity_id} className="interactive-row p-5 sm:p-6"><div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><p className="text-[11px] font-bold uppercase tracking-[.12em] text-sky-300">Rank #{item.rank}</p><h3 className="mt-1 text-lg font-semibold text-white">{names.get(item.entity_id) ?? item.entity_id}</h3></div><div className="flex flex-wrap items-center gap-2"><StatusPill tone={tone(item.severity)}>{item.severity} risk</StatusPill><span className="text-[13px] font-medium text-slate-300">Current Intelligence Score {item.score}/100{item.raw_score !== item.score ? ` · raw ${item.raw_score}` : ""}</span></div></div><div className="mt-5 grid gap-5 lg:grid-cols-3"><AnalysisList title={reminderPlan ? "Why it is eligible" : "Why it matched"} items={item.facts} empty="No material factual factor was recorded." /><AnalysisList title="Actionability and workflow state" items={[...(item.blocker ? [item.blocker] : ["No current action blocker detected"]), ...(item.stored_workflow_priority ? [`Stored workflow priority: ${label(item.stored_workflow_priority)}`] : [])]} empty="" /><div><p className="text-[11px] font-bold uppercase tracking-[.12em] text-slate-400">Current recommended action</p><p className="mt-2 text-[13px] font-medium leading-6 text-slate-200">{item.decision}</p>{onOpenTarget && <button type="button" onClick={() => onOpenTarget(result.interpreted_intent.query.entity === "RECOVERY_CASES" ? "RECOVERY_CASE" : "CUSTOMER", item.entity_id)} className="mt-3 text-xs font-semibold text-sky-300 hover:text-sky-200">Open supporting record →</button>}</div></div></article>)}</div></Panel>;
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
  return [...query.risk_levels.map((level) => `${label(level)} risk`), ...(query.exact_reference ? [`Exact reference ${query.exact_reference}`] : []), ...booleans.filter(([value]) => value === true).map(([, text]) => text), ...(query.min_days_overdue !== null ? [`At least ${query.min_days_overdue} days overdue`] : []), ...(query.max_days_overdue !== null ? [`At most ${query.max_days_overdue} days overdue`] : []), ...(query.min_score !== null ? [`Score at least ${query.min_score}`] : []), ...(query.max_score !== null ? [`Score at most ${query.max_score}`] : []), ...(query.min_exposure !== null ? [`Amount at least INR ${query.min_exposure}`] : []), ...(query.max_exposure !== null ? [`Amount at most INR ${query.max_exposure}`] : [])];
}

function queryExclusions(result: CommandResult): string[] {
  const query = result.interpreted_intent.query;
  const booleans = [[query.overdue, "No overdue exposure"], [query.broken_promise, "Broken promises"], [query.active_promise, "Active promises"], [query.active_dispute, "Active disputes"], [query.partial_payment, "Partial payments"], [query.recent_payment, "Recent payments"], [query.actionable, "Actionable records"], [query.blocked, "Blocked records"], [query.monitoring, "Monitoring records"]] as const;
  return booleans.filter(([value]) => value === false).map(([, text]) => text);
}

function queryOrder(result: CommandResult): string {
  const query = result.interpreted_intent.query;
  if (query.entity === "PAYMENTS") return query.descending ? "Latest payment date" : "Oldest payment date";
  if (query.entity === "INVOICES" && query.sort_by === "RISK_SCORE") return query.descending ? "Latest due date" : "Earliest due date";
  const names = { RISK_SCORE: "current intelligence score", TOTAL_EXPOSURE: "total exposure", OVERDUE_EXPOSURE: "overdue exposure", DAYS_OVERDUE: "oldest invoice age", LAST_PAYMENT: "latest payment activity" };
  return `${query.descending ? "Highest" : "Lowest"} ${names[query.sort_by]}`;
}

function Metric({ label: metricLabel, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-white/[.07] bg-white/[.025] p-3"><p className="text-[10px] uppercase tracking-[.12em] text-slate-600">{metricLabel}</p><p className="mt-2 text-base font-semibold text-white">{value}</p></div>;
}
