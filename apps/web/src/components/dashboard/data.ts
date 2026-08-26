import { apiFetch } from "@/lib/api";
import type { IntelligenceResult } from "@/lib/intelligence-api";

export type Portfolio = { simulation_date: string | null; total_outstanding_amount: string; total_invoices: number; total_customers: number };
export type Recovery = { overdue_exposure: string; broken_promise_exposure: string; cases_eligible_for_recovery: number; cases_requiring_attention?: number; cases_awaiting_payment: number; cases_blocked_by_dispute: number; escalated_cases: number; open_cases?: number; active_cases?: number; total_cases: number };
export type Customer = { id: string; name: string; account_reference: string; outstanding_amount: string };
export type CaseApi = { case_id: string; customer_id: string; customer_name: string; evaluation: { derived_state: string; invoice: { outstanding_amount: string; days_overdue: number } | null; promises: { state: string }[]; active_dispute: boolean; eligibility: { allowed: boolean; blocking_reasons: string[] }; next_factual_condition: string } };
export type Recommendation = { case_id: string; recommended_action: string; priority: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"; human_approval_required: boolean; factual_reasons: string[]; blockers: string[]; relevant_exposure: string; relevant_days_overdue: number; operator_explanation: string };
export type SimState = { cycle: number; simulation_date: string; tick_interval_seconds: number };
export type SimulationEvent = { id: string; cycle: number; type: string; customer_id: string | null; invoice_id: string | null; case_id: string | null; metadata: Record<string, string>; occurred_at: string };
export type SimulationTickEvent = { id: string; type: string; customer_id: string | null; invoice_id: string | null; case_id: string | null; metadata: Record<string, string | number> };
export type IntelligenceTransition = {
  entity_type: "CUSTOMER" | "RECOVERY_CASE";
  entity_id: string;
  entity_name: string;
  simulation_cycle: number;
  related_event_id: string;
  related_event_type: string;
  previous_score: number | null;
  current_score: number;
  score_direction: "INCREASED" | "DECREASED" | "UNCHANGED";
  previous_risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | null;
  current_risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  previous_recommendation: string | null;
  current_recommendation: string;
  current_recommendation_title: string;
  current_recommendation_explanation: string;
  operator_next_step: string | null;
  workflow_effect: string | null;
  signals_added: string[];
  signals_removed: string[];
  classifications: string[];
  change_direction: "WORSENED" | "IMPROVED" | "UNCHANGED";
  material: boolean;
  what_changed: string;
  why_intelligence_changed: string;
  decision_impact: string;
  operator_significance: string;
  related_events?: { id: string; type: string; family: string; role: "PRIMARY" | "SECONDARY" }[];
};
export type SimulationTickResult = {
  previous_cycle: number;
  previous_simulation_date: string;
  cycle: number;
  simulation_date: string;
  event_count: number;
  events: SimulationTickEvent[];
  intelligence_transitions: IntelligenceTransition[];
  recovery_synchronization: { cases_evaluated: number; cases_changed: number };
  generation: { seed: number; mode: "NORMAL" | "JUDGE"; primary_event_id: string; secondary_event_count: number; families: string[] };
  change_summary: { customers_affected: number; material_customers: number; recommendations_changed: number; recommendations_unchanged: number; blockers_added: number; blockers_removed: number };
};
export type LatestIntelligenceCycle = {
  cycle: number;
  event_count: number;
  customers_affected: number;
  material_customers: number;
  recommendations_changed: number;
  recommendations_unchanged: number;
  blockers_added: number;
  blockers_removed: number;
  transitions: IntelligenceTransition[];
};
export type RecoveryAction = {
  id: string;
  case_id: string;
  action_type: string;
  recommended_action: string | null;
  status: string;
  approval_status: string;
  human_approval_required: boolean;
  recommendation_context: { workflow_effect?: string; operator_next_step?: string; blockers?: string[] } | null;
  reason: string | null;
  decision_by: string | null;
  decision_reason: string | null;
  decision_at: string | null;
  executed_at: string | null;
  executed_by: string | null;
  operator_note: string | null;
  created_at: string | null;
};
export type ExternalPaymentRequest = { id: string; case_id: string; customer_id: string; invoice_id: string; provider: string; provider_mode: "DEMO" | "TEST"; provider_reference: string | null; provider_url: string | null; requested_amount: string; paid_amount: string; status: string; purpose: string; operator_id: string; failure_reason: string | null; created_at: string | null };
export type BatchRecoveryProof = {
  scope: { as_of_date: string; cycle: number; customer_count: number; invoice_count: number; case_count: number; earliest_due_date: string | null; provenance: string; definition: string };
  reconciliation: { starting_overdue_exposure: string; observed_recovery: string; remaining_overdue_exposure: string; recovery_rate: string; equation_holds: boolean; qualifying_payment_count: number; recovered_invoice_count: number; partially_recovered_invoice_count: number; remaining_open_overdue_invoice_count: number; fully_recovered_account_count: number; partially_recovered_account_count: number; measurement_note: string };
  stopping_rules: { deliberate_hold_count: number; active_dispute_hold_count: number; active_promise_hold_count: number; resolved_or_paid_case_count: number; blocked_action_count: number; approval_required_case_count: number; unresolved_exception_count: number; hold_evidence: { case_id: string; customer_id: string; invoice_id: string | null; customer_name: string; invoice_number: string | null; reasons: string[]; current_recommendation: string; provenance: string }[] };
  action_outcomes: { persisted_action_count: number; recommended: number; planned: number; pending_approval: number; approved: number; held: number; rejected: number; executed: number; cancelled: number; failed: number; payment_requests_created: number; provider_events_received: number; payments_persisted: number; duplicate_provider_events_ignored: number };
  baseline: { name: string; same_scope: boolean; same_operating_date: string; age_only_target_count: number; reconmate_immediate_action_count: number; reconmate_deliberate_hold_count: number; blocker_violations_avoided: number; limitation: string };
  payment_evidence: { payment_id: string; payment_reference: string | null; payment_date: string; amount: string; customer_id: string; case_id: string | null; invoice_id: string; invoice_number: string; provenance: string; provider_mode: string | null; request_reference: string | null; event_reference: string | null; provider_payment_reference: string | null; outstanding_before: string | null; outstanding_after: string | null }[];
};
export type ProviderEventEvidence = { id: string; payment_request_id: string; provider_event_id: string; provider_payment_reference: string; event_type: string; evidence: { source?: string; provider?: string; provider_mode?: string; provider_reference?: string; provider_payment_reference?: string; chronology?: string; financial_mutation?: string; outstanding_before?: string; outstanding_after?: string; score_before?: number; score_after?: number; recommendation_before?: string; recommendation_after?: string; duplicate_replay?: { ignored: boolean; original_event: string; financial_mutation: string; outstanding_before?: string; outstanding_after?: string } }; received_at: string };
export type EvidenceTimelineEntry = {
  id: string; occurred_at: string; category: "FACT_EVENT" | "INTELLIGENCE_REASSESSMENT" | "OPERATOR_ACTION" | "PROVIDER_EVENT";
  event_type: string; title: string; detail: string | null; customer_id: string | null; case_id: string | null; invoice_id: string | null;
  request_reference: string | null; event_reference: string | null; payment_reference: string | null;
  before: Record<string, string | number | null> | null; after: Record<string, string | number | null> | null;
  provenance: string; historical: boolean;
};
export type ProviderMode = { provider: string; mode: "DEMO" | "TEST"; label: string };
export type Invoice = { id: string; invoice_number: string; customer_id: string; issue_date: string; due_date: string; original_amount: string; outstanding_amount: string; status: string; source: "CSV_IMPORT" | "DEMO_SANDBOX"; latest_payment_amount: string | null; latest_payment_date: string | null; latest_payment_reference: string | null };
export type PriorityCase = { id: string; customerId: string; customerName: string; customerReference: string; amount: string; exposure: number; state: string; daysOverdue: number; promiseSignal: string; allowed: boolean; reason: string; recommendedAction: string; recommendationPriority: Recommendation["priority"]; recommendationReason: string; humanApprovalRequired: boolean; currentScore: number; currentRisk: IntelligenceResult["level"]; currentAction: string };
export type Workspace = {
  case_id: string;
  customer: { id: string; name: string; strategic: boolean };
  workflow: { stored_priority: string; recovery_state: string; opened_at: string | null; updated_at: string | null };
  invoice: { id: string; number: string; status: string; outstanding_amount: string; due_date: string } | null;
  recommendation: { recommended_action: string; priority: string; factual_reasons: string[]; blockers: string[]; relevant_days_overdue: number; human_approval_required: boolean; operator_explanation: string; operator_next_step: string; workflow_effect: string; communication_signals: { intent: string; confidence: string | null }[] };
  intelligence: { score: number; raw_score: number; calculated_at: string; level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"; recommendation: { action: string; title: string; explanation: string }; signals: { title: string; explanation: string; severity: string }[]; factors: { title: string; explanation: string; points: number; impact: string }[] };
  promises: { status: string; promised_amount: string; promised_date: string }[];
  payments?: { id: string; amount: string; payment_date: string; reference: string | null }[];
  communications: { id: string; direction: string; content: string; occurred_at: string; analyses: { intent?: string }[] }[];
  actions: { id: string; action_type: string; status: string; approval_status: string; recommended_action: string | null; human_approval_required: boolean; recommendation_context: { workflow_effect?: string; operator_next_step?: string; blockers?: string[] } | null; decision_by: string | null; decision_reason: string | null; decision_at: string | null; executed_at: string | null; created_at: string | null }[];
  external_payment_requests?: ExternalPaymentRequest[];
  provider_events?: ProviderEventEvidence[];
  evidence_timeline?: EvidenceTimelineEntry[];
  audit_events: { id: string; event_type: string; occurred_at: string }[];
};

export const formatMoney = (value: string | number) => {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "-";
  return amount >= 100000
    ? `INR ${(amount / 100000).toFixed(1)}L`
    : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(amount);
};

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await apiFetch(path);
  if (!response.ok) throw new Error(`Unable to load ${path.replaceAll("/", " ").trim()}.`);
  return response.json() as Promise<T>;
}

export function createPriorityQueue(customersList: Customer[], casesList: CaseApi[], recommendations: Recommendation[], intelligence: IntelligenceResult[]): PriorityCase[] {
  const customers = new Map(customersList.map((customer) => [customer.id, customer]));
  const cases = new Map(casesList.map((item) => [item.case_id, item]));
  const currentByCustomer = new Map(intelligence.map((item) => [item.entity_id, item]));

  return recommendations.flatMap((recommendation) => {
    const item = cases.get(recommendation.case_id);
    if (!item) return [];
    const customer = customers.get(item.customer_id);
    const current = currentByCustomer.get(item.customer_id);
    if (!current) return [];
    const invoice = item.evaluation.invoice;
    const promises = item.evaluation.promises;
    const exposure = Number(invoice?.outstanding_amount ?? customer?.outstanding_amount ?? "0");
    return {
      id: item.case_id,
      customerId: item.customer_id,
      customerName: item.customer_name,
      customerReference: customer?.account_reference ?? "Recovery account",
      amount: formatMoney(exposure),
      exposure,
      state: item.evaluation.derived_state,
      daysOverdue: invoice?.days_overdue ?? 0,
      promiseSignal: promises.some((promise) => promise.state === "ACTIVE") ? "Active promise" : promises.some((promise) => promise.state === "BROKEN") ? "Promise broken" : "No active promise",
      allowed: item.evaluation.eligibility.allowed,
      reason: item.evaluation.eligibility.allowed ? "Recovery eligible" : item.evaluation.eligibility.blocking_reasons.join(" / ").replaceAll("_", " "),
      recommendedAction: recommendation.recommended_action,
      recommendationPriority: recommendation.priority,
      recommendationReason: recommendation.operator_explanation,
      humanApprovalRequired: recommendation.human_approval_required,
      currentScore: current.score,
      currentRisk: current.level,
      currentAction: current.recommendation.action,
    };
  });
}
