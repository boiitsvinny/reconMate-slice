"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AppHeader } from "@/components/layout/app-header";
import { useCommandSession } from "@/components/intelligence/command-session";
import { apiUrl } from "@/lib/api";
import { getPortfolioIntelligence, type PortfolioIntelligence } from "@/lib/intelligence-api";
import { formatMoney as money, PriorityCase, SimState, SimulationTickResult } from "./data";
import { CaseWorkspace } from "./case-workspace";
import { LiveEventFeed } from "./live-event-feed";
import { OperationalIntelligenceHero } from "./operational-intelligence-hero";
import { PortfolioMetricCard } from "./portfolio-metric-card";
import { PortfolioSignals } from "./portfolio-signals";
import { RecommendationSafety } from "./recommendation-safety";
import { queryKeys, useCustomers, useInvalidateOperationalData, usePortfolio, usePortfolioIntelligence, useRecovery, useRecoveryQueue, useSimulationEvents, useSimulationState } from "./queries";
import { CycleFeedback, ResetFeedback, SimulationControl } from "./simulation-control";
import { TodaysOperationalFocus } from "./todays-operational-focus";

export function Dashboard() {
  const [auto, setAuto] = useState(false);
  const [lastTick, setLastTick] = useState<SimulationTickResult | null>(null);
  const [cycleFeedback, setCycleFeedback] = useState<CycleFeedback | undefined>();
  const [resetFeedback, setResetFeedback] = useState<ResetFeedback | undefined>();
  const [selected, setSelected] = useState<PriorityCase | null>(null);
  const operationInFlight = useRef(false);
  const queryClient = useQueryClient();
  const commandSession = useCommandSession();
  const portfolio = usePortfolio();
  const recovery = useRecovery();
  const customers = useCustomers();
  const simulation = useSimulationState();
  const events = useSimulationEvents();
  const intelligence = usePortfolioIntelligence();
  const recoveryQueue = useRecoveryQueue();
  const queries = [portfolio, recovery, customers, simulation, events];
  const connectedQueries = [...queries, intelligence, recoveryQueue.cases, recoveryQueue.recommendations];
  const dataReady = Boolean(portfolio.data && recovery.data && customers.data && simulation.data && events.data);
  const queryError = queries.find((query) => query.isError)?.error;
  const errorMessage = queryError instanceof Error ? queryError.message : queryError ? "Unable to connect to ReconMate." : null;
  const backgroundError = dataReady && Boolean(errorMessage);
  const connectionsHealthy = dataReady && connectedQueries.every((query) => !query.isError);
  const invalidateOperationalData = useInvalidateOperationalData();

  const tick = useMutation({
    onMutate: () => setResetFeedback(undefined),
    mutationFn: async () => {
      const before = await queryClient.fetchQuery({
        queryKey: queryKeys.portfolioIntelligence,
        queryFn: getPortfolioIntelligence,
        staleTime: 0,
      });
      const response = await fetch(apiUrl("/simulation/tick"), { method: "POST" });
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "Simulation tick failed.");
      }
      const result = await response.json() as SimulationTickResult;
      return { before, result };
    },
    onSuccess: async ({ before, result }) => {
      await invalidateOperationalData();
      const after = queryClient.getQueryData<PortfolioIntelligence>(queryKeys.portfolioIntelligence);
      const refreshFailed = [
        queryKeys.portfolio,
        queryKeys.portfolioIntelligence,
        queryKeys.recovery,
        queryKeys.customers,
        queryKeys.cases,
        queryKeys.recommendations,
        queryKeys.simulationState,
        queryKeys.simulationEvents,
      ].some((queryKey) => queryClient.getQueryState(queryKey)?.error);
      setLastTick(result);
      setCycleFeedback(buildCycleFeedback(result, before, after, refreshFailed));
    },
  });
  const resetDemo = useMutation({
    mutationFn: async () => {
      const response = await fetch(apiUrl("/simulation/reset"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmation: "RESET_DEMO_SIMULATION" }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "The demo simulation could not be reset.");
      }
      return response.json() as Promise<{ state: SimState; summary: Record<string, string | number> }>;
    },
    onSuccess: async (response) => {
      setAuto(false);
      setLastTick(null);
      setCycleFeedback(undefined);
      setSelected(null);
      commandSession.clearSession();
      await queryClient.resetQueries({ queryKey: queryKeys.all });
      const refreshedState = queryClient.getQueryData<SimState>(queryKeys.simulationState);
      const refreshFailed = [
        queryKeys.portfolio,
        queryKeys.portfolioIntelligence,
        queryKeys.recovery,
        queryKeys.customers,
        queryKeys.cases,
        queryKeys.recommendations,
        queryKeys.simulationState,
        queryKeys.simulationEvents,
      ].some((queryKey) => queryClient.getQueryState(queryKey)?.error);
      const baselineVerified = refreshedState?.cycle === response.state.cycle && refreshedState?.simulation_date === response.state.simulation_date;
      setResetFeedback(refreshFailed || !baselineVerified
        ? { status: "REFRESH_FAILED", message: `Baseline restored to cycle ${response.state.cycle}, but one or more dashboard views did not refresh. Retry before continuing the demo.` }
        : { status: "SUCCESS", message: `Demo baseline restored successfully: cycle ${response.state.cycle} / operating date ${response.state.simulation_date}.` });
    },
  });
  const busy = tick.isPending || resetDemo.isPending;
  const isUpdating = busy || connectedQueries.some((query) => query.isFetching);
  const mutateTick = tick.mutateAsync;
  const mutateReset = resetDemo.mutateAsync;

  const runTick = useCallback(async () => {
    if (operationInFlight.current) return;
    operationInFlight.current = true;
    try {
      await mutateTick();
    } catch {
      // Mutation state supplies the existing error presentation.
    } finally {
      operationInFlight.current = false;
    }
  }, [mutateTick]);

  const runReset = useCallback(async () => {
    if (operationInFlight.current) return;
    operationInFlight.current = true;
    setAuto(false);
    try {
      await mutateReset();
    } catch {
      // Mutation state supplies the reset error presentation.
    } finally {
      operationInFlight.current = false;
    }
  }, [mutateReset]);

  useEffect(() => {
    if (!auto || !simulation.data) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible" && !operationInFlight.current) void runTick();
    }, simulation.data.tick_interval_seconds * 1000);
    return () => window.clearInterval(timer);
  }, [auto, simulation.data, runTick]);

  const names = useMemo(() => new Map(customers.data?.map((customer) => [customer.id, customer.name]) ?? []), [customers.data]);
  const currentCycleEvents = events.data?.filter((event) => event.cycle === simulation.data?.cycle) ?? [];
  const latestPayment = currentCycleEvents.find((event) => event.metadata.payment_amount)?.metadata.payment_amount;
  const tickError = tick.error instanceof Error ? tick.error.message : null;
  const resetError = resetDemo.error instanceof Error ? resetDemo.error.message : null;
  const retry = () => Promise.all(queries.map((query) => query.refetch()));
  const intelligenceError = intelligence.error instanceof Error ? intelligence.error.message : intelligence.isError ? "Unable to load current portfolio intelligence." : null;
  const casesByCustomer = useMemo(() => {
    const result = new Map<string, PriorityCase>();
    for (const item of recoveryQueue.queue) {
      const current = result.get(item.customerId);
      const actionable = item.recommendedAction !== "NO_ACTION_REQUIRED" && item.state !== "RESOLVED";
      const currentActionable = current && current.recommendedAction !== "NO_ACTION_REQUIRED" && current.state !== "RESOLVED";
      if (!current || (actionable && !currentActionable)) result.set(item.customerId, item);
    }
    for (const event of lastTick?.events ?? []) {
      if (!event.customer_id || !event.case_id) continue;
      const affectedCase = recoveryQueue.queue.find((item) => item.id === event.case_id);
      if (affectedCase) result.set(event.customer_id, affectedCase);
    }
    return result;
  }, [lastTick, recoveryQueue.queue]);
  const affectedCustomerIds = useMemo(() => new Set(lastTick?.events.flatMap((event) => event.customer_id ? [event.customer_id] : []) ?? []), [lastTick]);
  const selectedAffected = Boolean(selected && lastTick?.events.some((event) => event.case_id === selected.id || event.customer_id === selected.customerId));
  const caseLinksLoading = recoveryQueue.cases.isLoading || recoveryQueue.recommendations.isLoading;
  const caseLinksError = recoveryQueue.cases.isError || recoveryQueue.recommendations.isError;

  return (
    <main className="min-h-screen overflow-x-hidden">
      <AppHeader connected={connectionsHealthy} updating={isUpdating} />
      <div className="mx-auto max-w-[1580px] px-4 py-6 pb-24 sm:px-6 sm:py-8 sm:pb-10 lg:px-10 lg:py-10">
        {!dataReady && !errorMessage && <DashboardLoading />}
        {!dataReady && errorMessage && (
          <div className="mb-6 flex flex-col justify-between gap-4 rounded-2xl border border-rose-300/20 bg-rose-300/[.06] p-5 sm:flex-row sm:items-center">
            <div>
              <p className="text-sm font-semibold text-rose-100">Portfolio data could not be loaded</p>
              <p className="mt-1 text-xs leading-5 text-rose-100/65">{errorMessage}</p>
            </div>
            <button type="button" onClick={() => void retry()} className="rounded-lg border border-rose-200/25 px-3.5 py-2 text-xs font-bold text-rose-50 transition hover:border-rose-200/50">Try again</button>
          </div>
        )}
        {backgroundError && <p className="mb-4 rounded-xl border border-amber-300/15 bg-amber-300/[.06] px-4 py-3 text-xs text-amber-100">Live refresh is delayed. Showing the last successful portfolio data.</p>}
        {tickError && <p className="mb-4 rounded-xl border border-rose-300/15 bg-rose-300/[.06] px-4 py-3 text-xs text-rose-100">{tickError}</p>}
        {resetError && <p className="mb-4 rounded-xl border border-rose-300/15 bg-rose-300/[.06] px-4 py-3 text-xs text-rose-100">Reset failed: {resetError}</p>}
        {portfolio.data && recovery.data && customers.data && simulation.data && events.data && (
          <>
            <section className="flex flex-col justify-between gap-7 pb-8 lg:flex-row lg:items-end">
              <div className="max-w-3xl">
                <p className="text-[11px] font-bold uppercase tracking-[.22em] text-sky-300">Operations command center</p>
                <h1 className="mt-4 text-3xl font-semibold tracking-[-.04em] text-white sm:text-4xl">Portfolio Recovery</h1>
                <p className="mt-4 max-w-2xl text-sm leading-6 text-slate-400">
                  {portfolio.data.total_customers} active B2B accounts / {portfolio.data.total_invoices} receivables / factual recovery position driven by the virtual operating date.
                </p>
              </div>
            </section>

            <section aria-label="Portfolio intelligence summary">
              <OperationalIntelligenceHero
                key={`intelligence-${intelligence.data?.calculated_at ?? "loading"}`}
                intelligence={intelligence.data}
                loading={intelligence.isLoading}
                error={intelligenceError}
                totalOutstanding={portfolio.data.total_outstanding_amount}
                overdueExposure={recovery.data.overdue_exposure}
                formatMoney={money}
                synchronizing={tick.isPending || intelligence.isFetching}
                synchronizedCycle={lastTick?.cycle}
              />
            </section>

            <TodaysOperationalFocus
              intelligence={intelligence.data}
              loading={intelligence.isLoading}
              error={intelligenceError}
              casesByCustomer={casesByCustomer}
              caseLinksLoading={caseLinksLoading}
              caseLinksError={caseLinksError}
              affectedCustomerIds={affectedCustomerIds}
              onSelectCase={setSelected}
              onRetry={() => void intelligence.refetch()}
            />

            <section aria-label="Important portfolio metrics" className="mt-7">
              <div className="mb-4 px-1">
                <p className="text-[10px] font-bold uppercase tracking-[.16em] text-sky-300">Operational position</p>
                <h2 className="mt-1.5 text-xl font-semibold tracking-[-.025em] text-white">Money and work requiring attention</h2>
              </div>
              <div className="hide-scrollbar flex snap-x snap-mandatory gap-4 overflow-x-auto pb-2 sm:grid sm:grid-cols-2 sm:overflow-visible sm:pb-0 xl:grid-cols-4">
              <PortfolioMetricCard className="min-w-[78vw] snap-start sm:min-w-0" label="Broken-promise exposure" state="At risk" value={money(recovery.data.broken_promise_exposure)} detail="Outstanding exposure tied to missed payment commitments." tone="amber" />
              <PortfolioMetricCard className="min-w-[78vw] snap-start sm:min-w-0" label="Recovery ready" state="Actionable" value={String(recovery.data.cases_eligible_for_recovery)} detail="Cases whose current facts allow operator recovery work." tone="blue" />
              <PortfolioMetricCard className="min-w-[78vw] snap-start sm:min-w-0" label="Recovered this cycle" state={latestPayment ? "Confirmed" : "No payment"} value={latestPayment ? money(latestPayment) : "-"} detail={latestPayment ? "A payment was persisted during the current simulation cycle." : "The current simulation cycle contains no payment event."} impact={latestPayment ? "Confirmed factual recovery" : undefined} tone="green" />
              <PortfolioMetricCard className="min-w-[78vw] snap-start sm:min-w-0" label="Attention required" state="Review" value={String(recovery.data.cases_requiring_attention ?? recovery.data.cases_eligible_for_recovery)} detail="Cases carrying an active factual attention condition." tone="red" />
              </div>
            </section>

            <section aria-label="Portfolio operations" className="mt-7 grid gap-7 xl:grid-cols-[minmax(0,1.5fr)_minmax(340px,.85fr)]">
              <LiveEventFeed events={events.data} customers={names} />
              <aside className="space-y-5">
                <PortfolioSignals signals={recovery.data} totalCases={recovery.data.total_cases} />
                <SimulationControl cycle={simulation.data.cycle} simulationDate={simulation.data.simulation_date} interval={simulation.data.tick_interval_seconds} busy={busy} resetting={resetDemo.isPending} auto={auto} feedback={cycleFeedback} resetFeedback={resetFeedback} onAutoChange={setAuto} onTick={() => void runTick()} onReset={() => void runReset()} />
              </aside>
            </section>
            <RecommendationSafety activeDisputes={recovery.data.cases_blocked_by_dispute} activePromises={recovery.data.cases_awaiting_payment} />
          </>
        )}
      </div>
      {selected && <CaseWorkspace item={selected} onClose={() => setSelected(null)} liveVersion={simulation.data?.cycle ?? 0} affected={selectedAffected} />}
    </main>
  );
}

function buildCycleFeedback(
  result: SimulationTickResult,
  before: PortfolioIntelligence,
  after: PortfolioIntelligence | undefined,
  refreshFailed: boolean,
): CycleFeedback {
  const event = result.events[0];
  const beforeById = new Map(before.customers.map((item) => [item.entity_id, item]));
  const afterById = new Map(after?.customers.map((item) => [item.entity_id, item]) ?? []);
  const previous = event?.customer_id ? beforeById.get(event.customer_id) : undefined;
  const current = event?.customer_id ? afterById.get(event.customer_id) : undefined;
  const customer = current?.entity_name ?? previous?.entity_name ?? "Portfolio account";
  const eventLabel = event ? event.type.replaceAll("_", " ").toLowerCase() : "No factual event recorded";
  const eventSummary = `${customer}: ${eventLabel}. ${result.recovery_synchronization.cases_evaluated} cases re-evaluated${result.recovery_synchronization.cases_changed ? `; ${result.recovery_synchronization.cases_changed} recovery state change${result.recovery_synchronization.cases_changed === 1 ? "" : "s"}` : ""}.`;

  if (refreshFailed || !after || after.calculated_at !== result.simulation_date) {
    return {
      status: "REFRESH_FAILED",
      headline: `Cycle ${result.cycle} completed; dashboard refresh is incomplete`,
      event: eventSummary,
      summary: "The factual event was persisted, but ReconMate could not verify every refreshed intelligence view. Retry the page data before treating it as current.",
      changes: [],
    };
  }

  const changes: string[] = [];
  if (previous && current && previous.level !== current.level) changes.push(`Risk changed: ${previous.level} → ${current.level}`);
  if (previous && current && previous.recommendation.action !== current.recommendation.action) changes.push(`Recommendation changed: ${previous.recommendation.action} → ${current.recommendation.action}`);
  const beforeRank = event?.customer_id ? before.highest_priority.findIndex((item) => item.entity_id === event.customer_id) : -1;
  const afterRank = event?.customer_id ? after.highest_priority.findIndex((item) => item.entity_id === event.customer_id) : -1;
  if (afterRank >= 0 && afterRank < 5 && (beforeRank < 0 || beforeRank >= 5)) changes.push("Added to Today's Operational Focus");
  else if (beforeRank >= 0 && afterRank >= 0 && beforeRank !== afterRank && afterRank < 5) changes.push(`Operational focus rank changed: ${beforeRank + 1} → ${afterRank + 1}`);

  return changes.length > 0
    ? {
        status: "MATERIAL_CHANGE",
        headline: `Cycle ${result.cycle} completed successfully`,
        event: eventSummary,
        summary: "ReconMate detected a material operational intelligence change.",
        changes,
      }
    : {
        status: "NO_MATERIAL_CHANGE",
        headline: `Cycle ${result.cycle} completed successfully`,
        event: eventSummary,
        summary: "ReconMate re-evaluated the portfolio. No material intelligence changes were detected.",
        changes: [],
      };
}

function DashboardLoading() {
  return (
    <div aria-label="Loading portfolio dashboard" role="status" className="animate-pulse space-y-7">
      <span className="sr-only">Loading live portfolio data</span>
      <div className="flex items-end justify-between gap-8">
        <div className="space-y-3"><div className="h-3 w-40 bg-white/[.06]" /><div className="h-10 w-72 bg-white/[.06]" /><div className="h-4 w-96 max-w-full bg-white/[.04]" /></div>
        <div className="hidden h-32 w-96 rounded-2xl bg-white/[.04] lg:block" />
      </div>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.55fr)_minmax(360px,.8fr)]"><div className="h-64 rounded-2xl bg-white/[.04]" /><div className="h-64 rounded-2xl bg-white/[.04]" /></div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 4 }, (_, index) => <div key={index} className="h-36 rounded-2xl bg-white/[.035]" />)}</div>
      <div className="h-96 rounded-2xl bg-white/[.035]" />
    </div>
  );
}
