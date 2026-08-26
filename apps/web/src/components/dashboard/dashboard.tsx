"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AppHeader } from "@/components/layout/app-header";
import { useCommandSession } from "@/components/intelligence/command-session";
import { useInsightMode } from "@/components/intelligence/insight-mode";
import { apiFetch } from "@/lib/api";
import { formatMoney as money, PriorityCase, SimState, SimulationTickResult } from "./data";
import { CaseWorkspace } from "./case-workspace";
import { CustomerPreview, useCasePreview } from "./customer-preview";
import { LiveEventFeed } from "./live-event-feed";
import { HomeRecoveryQueue } from "./home-recovery-queue";
import { OperationalIntelligenceHero } from "./operational-intelligence-hero";
import { PortfolioMetricCard } from "./portfolio-metric-card";
import { PortfolioSignals } from "./portfolio-signals";
import { RecommendationSafety } from "./recommendation-safety";
import { queryKeys, useCustomers, useInvalidateOperationalData, useLatestIntelligenceCycle, usePortfolio, usePortfolioIntelligence, useRecovery, useRecoveryQueue, useSimulationEvents, useSimulationState } from "./queries";
import { CycleFeedback, ResetFeedback, SimulationControl } from "./simulation-control";
import { AIPriorities } from "./todays-operational-focus";

export function Dashboard() {
  const { enabled: inspectionEnabled } = useInsightMode();
  const [auto, setAuto] = useState(false);
  const [lastTick, setLastTick] = useState<SimulationTickResult | null>(null);
  const [cycleFeedback, setCycleFeedback] = useState<CycleFeedback | undefined>();
  const [resetFeedback, setResetFeedback] = useState<ResetFeedback | undefined>();
  const [tickPhase, setTickPhase] = useState<"STARTING" | "APPLYING_EVENTS" | "REEVALUATING" | "SYNCHRONIZING" | "TAKING_LONGER">();
  const [selected, setSelected] = useState<PriorityCase | null>(null);
  const { preview, openPreview, closePreview } = useCasePreview();
  const operationInFlight = useRef(false);
  const queryClient = useQueryClient();
  const commandSession = useCommandSession();
  const portfolio = usePortfolio();
  const recovery = useRecovery();
  const customers = useCustomers();
  const simulation = useSimulationState();
  const events = useSimulationEvents();
  const intelligence = usePortfolioIntelligence();
  const latestIntelligenceCycle = useLatestIntelligenceCycle();
  const recoveryQueue = useRecoveryQueue();
  const queries = [portfolio, recovery, customers, simulation, events];
  const connectedQueries = [...queries, intelligence, latestIntelligenceCycle, recoveryQueue.cases, recoveryQueue.recommendations];
  const dataReady = Boolean(portfolio.data && recovery.data && customers.data && simulation.data && events.data);
  const queryError = queries.find((query) => query.isError)?.error;
  const errorMessage = queryError instanceof Error ? queryError.message : queryError ? "Unable to connect to ReconMate." : null;
  const backgroundError = dataReady && Boolean(errorMessage);
  const connectionsHealthy = dataReady && connectedQueries.every((query) => !query.isError);
  const invalidateOperationalData = useInvalidateOperationalData();

  const tick = useMutation({
    onMutate: () => { setResetFeedback(undefined); setTickPhase("STARTING"); },
    mutationFn: async () => {
      const response = await apiFetch("/simulation/tick", { method: "POST" }, 90_000);
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "Simulation tick failed.");
      }
      const result = await response.json() as SimulationTickResult;
      return result;
    },
    onSuccess: async (result) => {
      setTickPhase("SYNCHRONIZING");
      await invalidateOperationalData();
      const refreshFailed = [
        queryKeys.portfolio,
        queryKeys.portfolioIntelligence,
        queryKeys.recovery,
        queryKeys.customers,
        queryKeys.cases,
        queryKeys.recommendations,
        queryKeys.simulationState,
        queryKeys.simulationEvents,
        queryKeys.latestIntelligenceCycle,
      ].some((queryKey) => queryClient.getQueryState(queryKey)?.error);
      setLastTick(result);
      setCycleFeedback(buildCycleFeedback(result, refreshFailed));
    },
    onSettled: () => setTickPhase(undefined),
  });
  const resetDemo = useMutation({
    mutationFn: async () => {
      const response = await apiFetch("/simulation/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmation: "RESET_DEMO_SIMULATION" }),
      }, 90_000);
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
      closePreview();
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
        queryKeys.latestIntelligenceCycle,
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
    const applyingTimer = window.setTimeout(() => setTickPhase("APPLYING_EVENTS"), 800);
    const evaluationTimer = window.setTimeout(() => setTickPhase("REEVALUATING"), 3_000);
    const longTimer = window.setTimeout(() => setTickPhase("TAKING_LONGER"), 12_000);
    try {
      await mutateTick();
    } catch {
      // Mutation state supplies the existing error presentation.
    } finally {
      window.clearTimeout(applyingTimer);
      window.clearTimeout(evaluationTimer);
      window.clearTimeout(longTimer);
      operationInFlight.current = false;
    }
  }, [mutateTick]);

  const reconcile = useCallback(() => {
    void invalidateOperationalData();
  }, [invalidateOperationalData]);

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
  const recoveredThisCycle = currentCycleEvents.reduce((sum, event) => sum + Number(event.metadata.payment_amount ?? 0), 0);
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
  const latestCycleSnapshot = lastTick ? {
    cycle: lastTick.cycle,
    event_count: lastTick.event_count,
    customers_affected: lastTick.change_summary.customers_affected,
    material_customers: lastTick.change_summary.material_customers,
    recommendations_changed: lastTick.change_summary.recommendations_changed,
    recommendations_unchanged: lastTick.change_summary.recommendations_unchanged,
    blockers_added: lastTick.change_summary.blockers_added,
    blockers_removed: lastTick.change_summary.blockers_removed,
    transitions: lastTick.intelligence_transitions,
  } : latestIntelligenceCycle.data ?? null;
  const visibleTransitions = latestCycleSnapshot?.transitions ?? [];
  const selectedAffected = Boolean(selected && lastTick?.events.some((event) => event.case_id === selected.id || event.customer_id === selected.customerId));
  const selectedTransition = selected ? visibleTransitions.find((transition) => transition.entity_type === "RECOVERY_CASE" && transition.entity_id === selected.id) : undefined;
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
            <header className="mb-5 max-w-4xl">
              <p className="text-[10px] font-bold uppercase tracking-[.2em] text-sky-300">Live revenue recovery</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-[-.04em] text-white sm:text-4xl">Receivables, continuously reassessed</h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">ReconMate watches {portfolio.data.total_customers} customer accounts and changes recovery decisions when payment, promise, dispute, and behaviour evidence changes.</p>
            </header>

            <section aria-label="Top portfolio metrics" className="mb-5">
              <div className="hide-scrollbar flex snap-x snap-mandatory gap-3 overflow-x-auto pb-1 sm:grid sm:grid-cols-2 sm:overflow-visible xl:grid-cols-4">
                <PortfolioMetricCard className="min-w-[76vw] snap-start sm:min-w-0" label="Total outstanding" value={money(portfolio.data.total_outstanding_amount)} detail={`${portfolio.data.total_invoices} live receivables across the portfolio.`} tone="blue" />
                <PortfolioMetricCard className="min-w-[76vw] snap-start sm:min-w-0" label="Amount at risk" state="Needs attention" value={money(recovery.data.overdue_exposure)} detail="Current overdue exposure—not every balance requires the same action." tone="red" />
                <PortfolioMetricCard className="min-w-[76vw] snap-start sm:min-w-0" label="Recovered this cycle" state={recoveredThisCycle > 0 ? "Confirmed" : "No payment event"} value={recoveredThisCycle > 0 ? money(recoveredThisCycle) : "—"} detail="Sum of persisted payment events in the current operating cycle." tone="green" />
                <PortfolioMetricCard className="min-w-[76vw] snap-start sm:min-w-0" label="Active cases" value={String(recovery.data.active_cases ?? recovery.data.total_cases)} detail="Open recovery work currently monitored by ReconMate." tone="amber" />
              </div>
            </section>

            <section aria-label="ReconMate intelligence summary">
              <OperationalIntelligenceHero
                intelligence={intelligence.data}
                recovery={recovery.data}
                latestCycle={latestCycleSnapshot}
                approvals={recoveryQueue.queue.filter((item) => item.humanApprovalRequired && item.state !== "RESOLVED").length}
                recoveredThisCycle={recoveredThisCycle > 0 ? money(recoveredThisCycle) : "—"}
                evaluationUpdatedAt={intelligence.dataUpdatedAt}
                loading={intelligence.isLoading}
                error={intelligenceError}
                synchronizing={tick.isPending || intelligence.isFetching}
              />
            </section>

            <AIPriorities
              intelligence={intelligence.data}
              loading={intelligence.isLoading}
              error={intelligenceError}
              transitions={visibleTransitions}
              casesByCustomer={casesByCustomer}
              caseLinksLoading={caseLinksLoading}
              caseLinksError={caseLinksError}
              onSelectCase={openPreview}
            />

            {intelligence.data && <HomeRecoveryQueue items={recoveryQueue.queue} intelligence={intelligence.data} transitions={visibleTransitions} events={events.data} onSelect={openPreview} />}

            {inspectionEnabled && <section aria-label="Demo inspection tools" className="mt-7 grid gap-7 xl:grid-cols-[minmax(0,1.5fr)_minmax(340px,.85fr)]">
              <LiveEventFeed events={events.data} customers={names} onOpenCase={(caseId) => {
                const item = recoveryQueue.queue.find((candidate) => candidate.id === caseId);
                if (!item) return false;
                openPreview(item);
                return true;
              }} />
              <aside className="space-y-5">
                <PortfolioSignals signals={recovery.data} totalCases={recovery.data.total_cases} />
                <SimulationControl cycle={simulation.data.cycle} simulationDate={simulation.data.simulation_date} interval={simulation.data.tick_interval_seconds} busy={busy} resetting={resetDemo.isPending} auto={auto} feedback={cycleFeedback} resetFeedback={resetFeedback} phase={tickPhase} onAutoChange={setAuto} onTick={() => void runTick()} onReset={() => void runReset()} onReconcile={reconcile} />
              </aside>
            </section>}
            {inspectionEnabled && <RecommendationSafety activeDisputes={recovery.data.cases_blocked_by_dispute} activePromises={recovery.data.cases_awaiting_payment} />}
          </>
        )}
      </div>
      <CustomerPreview preview={preview} onClose={closePreview} onViewMore={(item) => { closePreview(); setSelected(item); }} />
      {selected && <CaseWorkspace item={selected} onClose={() => setSelected(null)} liveVersion={simulation.data?.cycle ?? 0} affected={selectedAffected} transition={selectedTransition} />}
    </main>
  );
}

function buildCycleFeedback(result: SimulationTickResult, refreshFailed: boolean): CycleFeedback {
  const transitions = result.intelligence_transitions.filter((item) => item.entity_type === "CUSTOMER").sort((left, right) => Number(right.material) - Number(left.material));
  const transition = transitions[0] ?? result.intelligence_transitions[0];
  const customer = transition?.entity_name ?? "Portfolio account";
  const eventLabel = result.events.length ? result.events.map((item) => `${item.metadata.role === "PRIMARY" ? "Primary" : "Secondary"}: ${item.type.replaceAll("_", " ").toLowerCase()}`).join(" / ") : "No factual event recorded";
  const eventSummary = `${customer}: ${eventLabel}. ${result.recovery_synchronization.cases_evaluated} cases re-evaluated${result.recovery_synchronization.cases_changed ? `; ${result.recovery_synchronization.cases_changed} recovery state change${result.recovery_synchronization.cases_changed === 1 ? "" : "s"}` : ""}.`;

  if (refreshFailed) {
    return { status: "REFRESH_FAILED", headline: `Cycle ${result.cycle} completed; dashboard refresh is incomplete`, event: eventSummary, summary: "The factual events and backend intelligence comparison completed, but one or more refreshed dashboard views failed.", changes: [], transition, transitions, portfolio: cyclePortfolio(result) };
  }
  const changes = transition?.classifications.filter((item) => item !== "NO_MATERIAL_CHANGE").map((item) => item.replaceAll("_", " ")) ?? [];
  return transition?.material
    ? { status: "MATERIAL_CHANGE", headline: `Cycle ${result.cycle}: intelligence ${transition.change_direction.toLowerCase()}`, event: eventSummary, summary: transition.operator_significance, changes, transition, transitions, portfolio: cyclePortfolio(result) }
    : { status: "NO_MATERIAL_CHANGE", headline: `Cycle ${result.cycle}: no material intelligence change`, event: eventSummary, summary: transition?.operator_significance ?? "ReconMate re-evaluated the affected records without changing a material decision.", changes: [], transition, transitions, portfolio: cyclePortfolio(result) };
}

function cyclePortfolio(result: SimulationTickResult): CycleFeedback["portfolio"] {
  return { previousCycle: result.previous_cycle, cycle: result.cycle, previousDate: result.previous_simulation_date, date: result.simulation_date, eventCount: result.event_count, customersAffected: result.change_summary.customers_affected, materialCustomers: result.change_summary.material_customers, recommendationsChanged: result.change_summary.recommendations_changed, recommendationsUnchanged: result.change_summary.recommendations_unchanged, families: result.generation.families, seed: result.generation.seed };
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
