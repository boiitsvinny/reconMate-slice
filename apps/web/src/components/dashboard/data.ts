import { apiUrl } from "@/lib/api";

export type Portfolio = { simulation_date: string | null; total_outstanding_amount: string; total_invoices: number; total_customers: number };
export type Recovery = { overdue_exposure: string; broken_promise_exposure: string; cases_eligible_for_recovery: number; cases_requiring_attention?: number; cases_awaiting_payment: number; cases_blocked_by_dispute: number; escalated_cases: number; total_cases: number };
export type Customer = { id: string; name: string; account_reference: string; outstanding_amount: string };
export type CaseApi = { case_id: string; customer_id: string; customer_name: string; evaluation: { derived_state: string; invoice: { outstanding_amount: string; days_overdue: number } | null; promises: { state: string }[]; active_dispute: boolean; eligibility: { allowed: boolean; blocking_reasons: string[] }; next_factual_condition: string } };
export type Recommendation = { case_id: string; recommended_action: string; priority: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"; human_approval_required: boolean; factual_reasons: string[]; blockers: string[]; relevant_exposure: string; relevant_days_overdue: number; operator_explanation: string };
export type SimState = { cycle: number; simulation_date: string; tick_interval_seconds: number };
export type Invoice = { id: string; invoice_number: string; customer_id: string; due_date: string; outstanding_amount: string; status: string };
export type PriorityCase = { id: string; customerId: string; customerName: string; customerReference: string; amount: string; exposure: number; state: string; daysOverdue: number; promiseSignal: string; allowed: boolean; reason: string; recommendedAction: string; recommendationPriority: Recommendation["priority"]; recommendationReason: string; humanApprovalRequired: boolean };

export const formatMoney = (value: string | number) => {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "-";
  return amount >= 100000
    ? `INR ${(amount / 100000).toFixed(1)}L`
    : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(amount);
};

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(apiUrl(path));
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
