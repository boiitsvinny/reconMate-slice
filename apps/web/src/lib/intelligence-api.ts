import { apiFetch } from "@/lib/api";

export type PriorityLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type CommandIntentType =
  | "PORTFOLIO_ANALYSIS"
  | "CUSTOMER_ANALYSIS"
  | "CASE_ANALYSIS"
  | "PRIORITIZE_CASES"
  | "PREPARE_FOLLOW_UPS"
  | "PREPARE_RECOVERY_ACTIONS"
  | "PREPARE_PAYMENT_REMINDERS"
  | "EXPLAIN_RECOMMENDATION"
  | "REVIEW_BROKEN_PROMISES"
  | "UNKNOWN";
export type ExecutionMode = "READ_ONLY" | "PREPARE" | "CONFIRMATION_REQUIRED" | "EXECUTED";
export type ProposalStatus = "ANALYZED" | "PREPARED" | "AWAITING_CONFIRMATION" | "EXECUTED" | "NOT_EXECUTABLE" | "FAILED";

export type IntelligenceSignal = {
  type: string;
  severity: PriorityLevel;
  title: string;
  explanation: string;
  contributing_value: string | number | null;
  calculated_at: string;
};

export type ContributingFactor = {
  type: string;
  title: string;
  impact: PriorityLevel;
  points: number;
  explanation: string;
  contributing_value: string | number | null;
};

export type IntelligenceResult = {
  entity_type: string;
  entity_id: string;
  entity_name: string;
  calculated_at: string;
  score: number;
  raw_score: number;
  level: PriorityLevel;
  metrics: {
    total_outstanding_amount: string;
    overdue_exposure: string;
    overdue_invoice_count: number;
    max_days_overdue: number;
    broken_promise_count: number;
    active_promise_count: number;
    active_dispute_count: number;
    days_since_last_payment: number | null;
    active_recovery_case_count: number;
    stalled_recovery_case_count: number;
  };
  signals: IntelligenceSignal[];
  factors: ContributingFactor[];
  recommendation: {
    action: string;
    title: string;
    explanation: string;
    priority_level: PriorityLevel;
    operator_confirmation_required: boolean;
  };
};

export type PortfolioIntelligence = {
  calculated_at: string;
  customer_count: number;
  average_score: string;
  level_counts: Record<PriorityLevel, number>;
  highest_priority: IntelligenceResult[];
  customers: IntelligenceResult[];
};

export type CommandRequest = {
  command: string;
  context_customer_id?: string | null;
  context_case_id?: string | null;
};

export type CommandFilters = {
  top_n: number | null;
  risk_levels: PriorityLevel[];
  overdue_only: boolean;
  broken_promises_only: boolean;
  include_all: boolean;
};

export type StructuredQuery = {
  entity: "CUSTOMERS" | "RECOVERY_CASES";
  risk_levels: PriorityLevel[];
  overdue: boolean | null;
  broken_promise: boolean | null;
  active_promise: boolean | null;
  active_dispute: boolean | null;
  partial_payment: boolean | null;
  recent_payment: boolean | null;
  actionable: boolean | null;
  blocked: boolean | null;
  monitoring: boolean | null;
  min_days_overdue: number | null;
  max_days_overdue: number | null;
  min_score: number | null;
  max_score: number | null;
  min_exposure: string | null;
  max_exposure: string | null;
  sort_by: "RISK_SCORE" | "TOTAL_EXPOSURE" | "OVERDUE_EXPOSURE" | "DAYS_OVERDUE" | "LAST_PAYMENT";
  descending: boolean;
  limit: number | null;
  time_scope: "CURRENT" | "LATEST_CYCLE";
  count_only: boolean;
  explanation_requested: boolean;
};

export type QueryEvidence = {
  records_inspected: number;
  records_matched: number;
  records_excluded: number;
  records_returned: number;
  inspection_scope: {
    customers: number;
    invoices: number;
    promises: number;
    active_disputes: number;
    recovery_cases: number;
    latest_cycle_events: number;
  };
  ranking_policy: string[];
  exclusions: { reason: string; count: number }[];
  ranking: {
    entity_id: string;
    rank: number;
    score: number;
    raw_score: number;
    severity: PriorityLevel;
    stored_workflow_priority: string | null;
    facts: string[];
    blocker: string | null;
    decision: string;
  }[];
  latest_cycle: {
    cycle: number;
    event_count: number;
    customers_affected: number;
    material_customers: number;
    recommendations_changed: number;
    recommendations_unchanged: number;
    observations: string[];
  } | null;
};

export type ActionProposal = {
  proposal_id: string;
  action_type: string;
  target_type: string;
  target_id: string;
  title: string;
  explanation: string;
  priority: PriorityLevel;
  risk_level: PriorityLevel;
  execution_mode: ExecutionMode;
  executable: boolean;
  requires_confirmation: boolean;
  current_intelligence_score: number | null;
  current_intelligence_action: string | null;
  workflow_recommendation_action: string | null;
  reminder_artifact: ReminderArtifact | null;
  limitations: string[];
};

export type ReminderArtifact = {
  status: "PREPARED_FOR_REVIEW" | "BLOCKED_DISPUTE" | "DEFERRED_ACTIVE_PROMISE" | "RECOVERY_COMPLETE" | "NON_SENDABLE_POLICY" | "UNAVAILABLE";
  customer_name: string;
  account_reference: string;
  invoices: { invoice_number: string; outstanding_amount: string; due_date: string; days_overdue: number }[];
  total_outstanding: string;
  promise_state: string;
  dispute_state: string;
  intended_channel: string;
  purpose: string;
  tone: string;
  prepared_at: string;
  body: string | null;
  reason: string;
};

export type ActionOutcome = {
  proposal_id: string;
  status: ProposalStatus;
  message: string;
  recovery_action_id: string | null;
  recovery_action_status: string | null;
  recovery_action_created_at: string | null;
  workflow_effect: string | null;
};

export type CommandResult = {
  plan_id: string;
  interpreted_intent: {
    intent: CommandIntentType;
    confidence: number;
    scope: "PORTFOLIO" | "CUSTOMER" | "CASE";
    filters: CommandFilters;
    query: StructuredQuery;
    reasoning: string[];
    guidance: string | null;
  };
  understanding_summary: string;
  query_evidence: QueryEvidence;
  analyzed_entities: IntelligenceResult[];
  plan: {
    plan_id: string;
    created_at: string;
    expires_at: string | null;
    intent: CommandIntentType;
    entities: { entity_type: string; entity_id: string; display_name: string }[];
    filters: CommandFilters;
    reasoning: string[];
    proposed_actions: ActionProposal[];
    requires_confirmation: boolean;
    execution_mode: ExecutionMode;
  };
  outcomes: ActionOutcome[];
  warnings: string[];
  limitations: string[];
  audit: {
    plan_id: string;
    interpreted_intent: CommandIntentType;
    timestamp: string;
    proposal_count: number;
    execution_status: ExecutionMode;
  };
};

export type ConfirmationResult = {
  plan_id: string;
  execution_mode: ExecutionMode;
  outcomes: ActionOutcome[];
  warnings: string[];
  audit: CommandResult["audit"];
};

export class ApiRequestError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "ApiRequestError";
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(path, init, init?.method === "POST" ? 60_000 : undefined);
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new ApiRequestError(payload?.detail ?? `ReconMate API request failed (${response.status}).`, response.status);
  }
  return response.json() as Promise<T>;
}

export function submitCommand(payload: CommandRequest): Promise<CommandResult> {
  return requestJson("/commands", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function confirmCommand(
  planId: string,
  proposalIds: string[],
  operatorId = "web-operator",
): Promise<ConfirmationResult> {
  return requestJson(`/commands/${planId}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ operator_id: operatorId, proposal_ids: proposalIds }),
  });
}

export function getPortfolioIntelligence(): Promise<PortfolioIntelligence> {
  return requestJson("/intelligence/portfolio");
}
