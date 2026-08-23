"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppHeader } from "@/components/layout/app-header";
import { apiUrl } from "@/lib/api";
import { Customer, fetchJson, formatMoney as money, Portfolio, Recovery, SimState } from "./data";
import { IntelligenceBoundary } from "./intelligence-boundary";
import { LiveEventFeed, SimulationEvent } from "./live-event-feed";
import { PortfolioHealth } from "./portfolio-health";
import { PortfolioMetricCard } from "./portfolio-metric-card";
import { PortfolioSignals } from "./portfolio-signals";
import { SimulationControl } from "./simulation-control";

type DashboardData = { portfolio: Portfolio; recovery: Recovery; customers: Customer[]; simulation: SimState; events: SimulationEvent[] };

export function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [auto, setAuto] = useState(false);
  const [ticking, setTicking] = useState(false);
  const [lastResult, setLastResult] = useState("");
  const tickInFlight = useRef(false);

  const refresh = useCallback(async () => {
    const [portfolio, recovery, customers, simulation, events] = await Promise.all([
      fetchJson<Portfolio>("/portfolio/summary"), fetchJson<Recovery>("/recovery/portfolio/summary"), fetchJson<Customer[]>("/customers"),
      fetchJson<SimState>("/simulation/state"), fetchJson<SimulationEvent[]>("/simulation/events"),
    ]);
    setData({ portfolio, recovery, customers, simulation, events });
    setError(null);
  }, []);

  useEffect(() => {
    void refresh().catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Unable to connect to ReconMate."));
  }, [refresh]);

  const runTick = useCallback(async () => {
    if (tickInFlight.current) return;
    tickInFlight.current = true;
    setTicking(true);
    try {
      const response = await fetch(apiUrl("/simulation/tick"), { method: "POST" });
      if (!response.ok) throw new Error("Simulation tick failed.");
      const result = await response.json() as { cycle: number; event_count: number; events: SimulationEvent[] };
      setLastResult(`Cycle ${result.cycle}: ${result.event_count} persisted event${result.event_count === 1 ? "" : "s"}.`);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Simulation tick failed.");
    } finally {
      tickInFlight.current = false;
      setTicking(false);
    }
  }, [refresh]);

  useEffect(() => {
    if (!auto || !data) return;
    const timer = window.setInterval(() => {
      if (!tickInFlight.current) void runTick();
    }, data.simulation.tick_interval_seconds * 1000);
    return () => window.clearInterval(timer);
  }, [auto, data, runTick]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!tickInFlight.current) void refresh().catch(() => undefined);
    }, 30000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const names = useMemo(() => new Map(data?.customers.map((customer) => [customer.id, customer.name]) ?? []), [data?.customers]);
  const latestPayment = data?.events[0]?.metadata.payment_amount;

  return (
    <main className="min-h-screen overflow-x-hidden">
      <AppHeader connected={Boolean(data)} />
      <div className="mx-auto max-w-[1580px] px-4 py-8 sm:px-6 lg:px-10 lg:py-10">
        {!data && !error && <DashboardLoading />}
        {error && (
          <div className="mb-6 flex flex-col justify-between gap-4 rounded-2xl border border-rose-300/20 bg-rose-300/[.06] p-5 sm:flex-row sm:items-center">
            <div>
              <p className="text-sm font-semibold text-rose-100">Portfolio data could not be refreshed</p>
              <p className="mt-1 text-xs leading-5 text-rose-100/65">{error}{data ? " The last synchronized view remains available below." : ""}</p>
            </div>
            <button type="button" onClick={() => void refresh().catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Unable to connect to ReconMate."))} className="rounded-lg border border-rose-200/25 px-3.5 py-2 text-xs font-bold text-rose-50 transition hover:border-rose-200/50">Try again</button>
          </div>
        )}
        {data && (
          <>
            <section className="flex flex-col justify-between gap-7 pb-8 lg:flex-row lg:items-end">
              <div className="max-w-3xl">
                <p className="text-[11px] font-bold uppercase tracking-[.22em] text-sky-300">Operations command center</p>
                <h1 className="mt-4 text-3xl font-semibold tracking-[-.04em] text-white sm:text-4xl">Portfolio Recovery</h1>
                <p className="mt-4 max-w-2xl text-sm leading-6 text-slate-400">
                  {data.portfolio.total_customers} active B2B accounts / {data.portfolio.total_invoices} receivables / factual recovery position driven by the virtual operating date.
                </p>
              </div>
            </section>

            <section aria-label="Portfolio health">
              <PortfolioHealth
                totalOutstanding={data.portfolio.total_outstanding_amount}
                overdueExposure={data.recovery.overdue_exposure}
                totalCustomers={data.portfolio.total_customers}
                totalInvoices={data.portfolio.total_invoices}
                attentionCases={data.recovery.cases_requiring_attention ?? data.recovery.cases_eligible_for_recovery}
                formatMoney={money}
              />
            </section>

            <section aria-label="Important portfolio metrics" className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <PortfolioMetricCard label="Broken-promise exposure" value={money(data.recovery.broken_promise_exposure)} detail="Money at risk behind missed commitments" tone="amber" />
              <PortfolioMetricCard label="Recovery ready" value={String(data.recovery.cases_eligible_for_recovery)} detail="Cases currently eligible for operator action" tone="blue" />
              <PortfolioMetricCard label="Recovered this cycle" value={latestPayment ? money(latestPayment) : "-"} detail="Latest persisted payment event" impact={latestPayment ? "Confirmed factual recovery" : undefined} tone="green" />
              <PortfolioMetricCard label="Attention required" value={String(data.recovery.cases_requiring_attention ?? data.recovery.cases_eligible_for_recovery)} detail="Cases with a current factual condition" tone="red" />
            </section>

            <section aria-label="Portfolio operations" className="mt-7 grid gap-7 xl:grid-cols-[minmax(0,1.5fr)_minmax(340px,.85fr)]">
              <LiveEventFeed events={data.events} customers={names} />
              <aside className="space-y-5">
                <PortfolioSignals signals={data.recovery} totalCases={data.recovery.total_cases} />
                <IntelligenceBoundary />
                <SimulationControl cycle={data.simulation.cycle} interval={data.simulation.tick_interval_seconds} busy={ticking} auto={auto} lastResult={lastResult} onAutoChange={setAuto} onTick={() => void runTick()} />
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
