"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AppHeader } from "@/components/layout/app-header";
import { apiUrl } from "@/lib/api";
import { formatMoney as money, SimulationEvent } from "./data";
import { IntelligenceBoundary } from "./intelligence-boundary";
import { LiveEventFeed } from "./live-event-feed";
import { PortfolioHealth } from "./portfolio-health";
import { PortfolioMetricCard } from "./portfolio-metric-card";
import { PortfolioSignals } from "./portfolio-signals";
import { useCustomers, useInvalidateOperationalData, usePortfolio, useRecovery, useSimulationEvents, useSimulationState } from "./queries";
import { SimulationControl } from "./simulation-control";

export function Dashboard() {
  const [auto, setAuto] = useState(false);
  const [lastResult, setLastResult] = useState("");
  const tickInFlight = useRef(false);
  const portfolio = usePortfolio();
  const recovery = useRecovery();
  const customers = useCustomers();
  const simulation = useSimulationState();
  const events = useSimulationEvents();
  const queries = [portfolio, recovery, customers, simulation, events];
  const dataReady = Boolean(portfolio.data && recovery.data && customers.data && simulation.data && events.data);
  const queryError = queries.find((query) => query.isError)?.error;
  const errorMessage = queryError instanceof Error ? queryError.message : queryError ? "Unable to connect to ReconMate." : null;
  const backgroundError = dataReady && Boolean(errorMessage);
  const isUpdating = dataReady && queries.some((query) => query.isFetching);
  const invalidateOperationalData = useInvalidateOperationalData();

  const tick = useMutation({
    mutationFn: async () => {
      const response = await fetch(apiUrl("/simulation/tick"), { method: "POST" });
      if (!response.ok) throw new Error("Simulation tick failed.");
      return response.json() as Promise<{ cycle: number; event_count: number; events: SimulationEvent[] }>;
    },
    onSuccess: async (result) => {
      setLastResult(`Cycle ${result.cycle}: ${result.event_count} persisted event${result.event_count === 1 ? "" : "s"}.`);
      await invalidateOperationalData();
    },
  });
  const mutateTick = tick.mutateAsync;

  const runTick = useCallback(async () => {
    if (tickInFlight.current) return;
    tickInFlight.current = true;
    try {
      await mutateTick();
    } catch {
      // Mutation state supplies the existing error presentation.
    } finally {
      tickInFlight.current = false;
    }
  }, [mutateTick]);

  useEffect(() => {
    if (!auto || !simulation.data) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible" && !tickInFlight.current) void runTick();
    }, simulation.data.tick_interval_seconds * 1000);
    return () => window.clearInterval(timer);
  }, [auto, simulation.data, runTick]);

  const names = useMemo(() => new Map(customers.data?.map((customer) => [customer.id, customer.name]) ?? []), [customers.data]);
  const latestPayment = events.data?.[0]?.metadata.payment_amount;
  const tickError = tick.error instanceof Error ? tick.error.message : null;
  const retry = () => Promise.all(queries.map((query) => query.refetch()));

  return (
    <main className="min-h-screen overflow-x-hidden">
      <AppHeader connected={dataReady} updating={isUpdating} />
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

            <section aria-label="Portfolio health">
              <PortfolioHealth
                totalOutstanding={portfolio.data.total_outstanding_amount}
                overdueExposure={recovery.data.overdue_exposure}
                totalCustomers={portfolio.data.total_customers}
                totalInvoices={portfolio.data.total_invoices}
                attentionCases={recovery.data.cases_requiring_attention ?? recovery.data.cases_eligible_for_recovery}
                formatMoney={money}
              />
            </section>

            <section aria-label="Important portfolio metrics" className="hide-scrollbar mt-4 flex snap-x snap-mandatory gap-4 overflow-x-auto pb-2 sm:grid sm:grid-cols-2 sm:overflow-visible sm:pb-0 xl:grid-cols-4">
              <PortfolioMetricCard className="min-w-[78vw] snap-start sm:min-w-0" label="Broken-promise exposure" value={money(recovery.data.broken_promise_exposure)} detail="Money at risk behind missed commitments" tone="amber" />
              <PortfolioMetricCard className="min-w-[78vw] snap-start sm:min-w-0" label="Recovery ready" value={String(recovery.data.cases_eligible_for_recovery)} detail="Cases currently eligible for operator action" tone="blue" />
              <PortfolioMetricCard className="min-w-[78vw] snap-start sm:min-w-0" label="Recovered this cycle" value={latestPayment ? money(latestPayment) : "-"} detail="Latest persisted payment event" impact={latestPayment ? "Confirmed factual recovery" : undefined} tone="green" />
              <PortfolioMetricCard className="min-w-[78vw] snap-start sm:min-w-0" label="Attention required" value={String(recovery.data.cases_requiring_attention ?? recovery.data.cases_eligible_for_recovery)} detail="Cases with a current factual condition" tone="red" />
            </section>

            <section aria-label="Portfolio operations" className="mt-7 grid gap-7 xl:grid-cols-[minmax(0,1.5fr)_minmax(340px,.85fr)]">
              <LiveEventFeed events={events.data} customers={names} />
              <aside className="space-y-5">
                <PortfolioSignals signals={recovery.data} totalCases={recovery.data.total_cases} />
                <IntelligenceBoundary />
                <SimulationControl cycle={simulation.data.cycle} interval={simulation.data.tick_interval_seconds} busy={tick.isPending} auto={auto} lastResult={lastResult} onAutoChange={setAuto} onTick={() => void runTick()} />
              </aside>
            </section>
          </>
        )}
      </div>
    </main>
  );
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
