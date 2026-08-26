import { apiFetch } from "@/lib/api";

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
export type Invoice = { id: string; invoice_number: string; customer_id: string; issue_date: string; due_date: string; original_amount: string; outstanding_amount: string; status: string; source: "CSV_IMPORT" | "DEMO_SANDBOX" };
export type PriorityCase = { id: string; customerId: string; customerName: string; customerReference: string; amount: string; exposure: number; state: string; daysOverdue: number; promiseSignal: string; allowed: boolean; reason: string; recommendedAction: string; recommendationPriority: Recommendation["priority"]; recommendationReason: string; humanApprovalRequired: boolean };
export type Workspace = {
  customer: { name: string; strategic: boolean };
  workflow: { stored_priority: string; recovery_state: string; opened_at: string | null; updated_at: string | null };
  invoice: { number: string; status: string; outstanding_amount: string; due_date: string } | null;
  recommendation: { recommended_action: string; priority: string; factual_reasons: string[]; blockers: string[]; relevant_days_overdue: number; human_approval_required: boolean; operator_explanation: string; operator_next_step: string; workflow_effect: string; communication_signals: { intent: string; confidence: string | null }[] };
  intelligence: { score: number; raw_score: number; calculated_at: string; level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"; signals: { title: string; explanation: string; severity: string }[]; factors: { title: string; explanation: string; points: number; impact: string }[] };
  promises: { status: string; promised_amount: string; promised_date: string }[];
  payments?: { id: string; amount: string; payment_date: string; reference: string | null }[];
  communications: { id: string; direction: string; content: string; occurred_at: string; analyses: { intent?: string }[] }[];
  actions: { id: string; action_type: string; status: string; approval_status: string; recommended_action: string | null; human_approval_required: boolean; recommendation_context: { workflow_effect?: string; operator_next_step?: string; blockers?: string[] } | null; decision_by: string | null; decision_reason: string | null; decision_at: string | null; executed_at: string | null; created_at: string | null }[];
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

export function createPriorityQueue(customersList: Customer[], casesList: CaseApi[], recommendations: Recommendation[]): PriorityCase[] {
  const customers = new Map(customersList.map((customer) => [customer.id, customer]));
  const cases = new Map(casesList.map((item) => [item.case_id, item]));

  return recommendations.flatMap((recommendation) => {
    const item = cases.get(recommendation.case_id);
    if (!item) return [];
    const customer = customers.get(item.customer_id);
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
    };
  });
}
