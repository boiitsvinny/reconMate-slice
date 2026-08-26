"use client";

import { useCallback, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CaseApi, createPriorityQueue, Customer, ExternalPaymentRequest, fetchJson, Invoice, LatestIntelligenceCycle, Portfolio, ProviderMode, Recommendation, Recovery, RecoveryAction, SimState, SimulationEvent, Workspace } from "./data";
import { getPortfolioIntelligence } from "@/lib/intelligence-api";

export const LIVE_REFRESH_INTERVAL = 15_000;

export const queryKeys = {
  all: ["reconmate"] as const,
  portfolio: ["reconmate", "portfolio"] as const,
  portfolioIntelligence: ["reconmate", "portfolio-intelligence"] as const,
  recovery: ["reconmate", "recovery-summary"] as const,
  customers: ["reconmate", "customers"] as const,
  invoices: ["reconmate", "invoices"] as const,
  cases: ["reconmate", "cases"] as const,
  recommendations: ["reconmate", "recommendations"] as const,
  actions: ["reconmate", "actions"] as const,
  paymentRequests: ["reconmate", "payment-requests"] as const,
  providerMode: ["reconmate", "provider-mode"] as const,
  simulationState: ["reconmate", "simulation-state"] as const,
  simulationEvents: ["reconmate", "simulation-events"] as const,
  latestIntelligenceCycle: ["reconmate", "latest-intelligence-cycle"] as const,
  workspace: (caseId: string) => ["reconmate", "workspace", caseId] as const,
};

const liveQuery = { refetchInterval: LIVE_REFRESH_INTERVAL, refetchIntervalInBackground: false } as const;

export const usePortfolio = () => useQuery({ queryKey: queryKeys.portfolio, queryFn: () => fetchJson<Portfolio>("/portfolio/summary"), ...liveQuery });
export const usePortfolioIntelligence = () => useQuery({ queryKey: queryKeys.portfolioIntelligence, queryFn: getPortfolioIntelligence, ...liveQuery });
export const useRecovery = () => useQuery({ queryKey: queryKeys.recovery, queryFn: () => fetchJson<Recovery>("/recovery/portfolio/summary"), ...liveQuery });
export const useCustomers = () => useQuery({ queryKey: queryKeys.customers, queryFn: () => fetchJson<Customer[]>("/customers"), ...liveQuery });
export const useInvoices = () => useQuery({ queryKey: queryKeys.invoices, queryFn: () => fetchJson<Invoice[]>("/invoices"), ...liveQuery });
export const useCases = () => useQuery({ queryKey: queryKeys.cases, queryFn: () => fetchJson<CaseApi[]>("/recovery/cases"), ...liveQuery });
export const useRecommendations = () => useQuery({ queryKey: queryKeys.recommendations, queryFn: () => fetchJson<Recommendation[]>("/recovery/recommendations"), ...liveQuery });
export const useRecoveryActions = () => useQuery({ queryKey: queryKeys.actions, queryFn: () => fetchJson<RecoveryAction[]>("/recovery/actions"), ...liveQuery });
export const usePaymentRequests = () => useQuery({ queryKey: queryKeys.paymentRequests, queryFn: () => fetchJson<ExternalPaymentRequest[]>("/payment-provider/requests"), ...liveQuery });
export const useProviderMode = () => useQuery({ queryKey: queryKeys.providerMode, queryFn: () => fetchJson<ProviderMode>("/payment-provider/mode"), staleTime: 60_000 });
export const useSimulationState = () => useQuery({ queryKey: queryKeys.simulationState, queryFn: () => fetchJson<SimState>("/simulation/state"), ...liveQuery });
export const useSimulationEvents = () => useQuery({ queryKey: queryKeys.simulationEvents, queryFn: () => fetchJson<SimulationEvent[]>("/simulation/events"), ...liveQuery });
export const useLatestIntelligenceCycle = () => useQuery({ queryKey: queryKeys.latestIntelligenceCycle, queryFn: () => fetchJson<LatestIntelligenceCycle | null>("/simulation/intelligence/latest"), ...liveQuery });
export const useCaseWorkspace = (caseId: string) => useQuery({ queryKey: queryKeys.workspace(caseId), queryFn: () => fetchJson<Workspace>(`/recovery/cases/${caseId}/workspace`), refetchInterval: LIVE_REFRESH_INTERVAL, refetchIntervalInBackground: false });

export function useRecoveryQueue() {
  const customers = useCustomers();
  const cases = useCases();
  const recommendations = useRecommendations();
  const currentIntelligence = usePortfolioIntelligence();
  const queue = useMemo(() => customers.data && cases.data && recommendations.data && currentIntelligence.data ? createPriorityQueue(customers.data, cases.data, recommendations.data, currentIntelligence.data.customers) : [], [customers.data, cases.data, recommendations.data, currentIntelligence.data]);
  return { customers, cases, recommendations, currentIntelligence, queue };
}

export function useInvalidateOperationalData() {
  const queryClient = useQueryClient();
  return useCallback(() => queryClient.invalidateQueries({ queryKey: queryKeys.all }), [queryClient]);
}
