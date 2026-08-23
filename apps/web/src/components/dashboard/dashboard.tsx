"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppHeader } from "@/components/layout/app-header";
import { CaseWorkspace } from "./case-workspace";
import { IntelligenceBoundary } from "./intelligence-boundary";
import { InvoiceRegister } from "./invoice-register";
import { LiveEventFeed, SimulationEvent } from "./live-event-feed";
import { PortfolioMetricCard } from "./portfolio-metric-card";
import { PortfolioSignals } from "./portfolio-signals";
import { PriorityQueue } from "./priority-queue";
import { SimulationControl } from "./simulation-control";
import { apiUrl } from "@/lib/api";

type Portfolio = { simulation_date: string | null; total_outstanding_amount: string; total_invoices: number; total_customers: number };
type Recovery = { overdue_exposure: string; broken_promise_exposure: string; cases_eligible_for_recovery: number; cases_requiring_attention?: number; cases_awaiting_payment: number; cases_blocked_by_dispute: number; escalated_cases: number };
type Customer = { id: string; name: string; account_reference: string; outstanding_amount: string };
type CaseApi = { case_id: string; customer_id: string; customer_name: string; evaluation: { derived_state: string; invoice: { outstanding_amount: string; days_overdue: number } | null; promises: { state: string }[]; eligibility: { allowed: boolean; blocking_reasons: string[] } } };
type SimState = { cycle: number; simulation_date: string; tick_interval_seconds: number };
type Invoice = { id: string; invoice_number: string; customer_id: string; due_date: string; outstanding_amount: string; status: string };
type DashboardData = { portfolio: Portfolio; recovery: Recovery; customers: Customer[]; invoices: Invoice[]; cases: CaseApi[]; simulation: SimState; events: SimulationEvent[] };
export type PriorityCase = { id: string; customerId: string; customerName: string; customerReference: string; amount: string; state: string; daysOverdue: number; promiseSignal: string; allowed: boolean; reason: string };
const money = (value: string | number) => { const amount = Number(value); return Number.isFinite(amount) ? (amount >= 100000 ? `₹${(amount / 100000).toFixed(1)}L` : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(amount)) : "—"; };

export function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<PriorityCase | null>(null);
  const [auto, setAuto] = useState(false);
  const [ticking, setTicking] = useState(false);
  const [lastResult, setLastResult] = useState("");
  const [changedCases, setChangedCases] = useState<Set<string>>(new Set());
  const tickInFlight = useRef(false);
  const refresh = useCallback(async () => {
    const responses = await Promise.all(["/portfolio/summary", "/recovery/portfolio/summary", "/customers", "/invoices", "/recovery/cases", "/simulation/state", "/simulation/events"].map((path) => fetch(apiUrl(path))));
    if (responses.some((response) => !response.ok)) throw new Error("One or more portfolio services are unavailable.");
    const [portfolio, recovery, customers, invoices, cases, simulation, events] = await Promise.all(responses.map((response) => response.json()));
    setData({ portfolio, recovery, customers, invoices, cases, simulation, events }); setError(null);
  }, []);
  useEffect(() => { void refresh().catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Unable to connect to ReconMate.")); }, [refresh]);
  const runTick = useCallback(async () => {
    if (tickInFlight.current) return;
    tickInFlight.current = true; setTicking(true);
    try {
      const response = await fetch(apiUrl("/simulation/tick"), { method: "POST" });
      if (!response.ok) throw new Error("Simulation tick failed.");
      const result = await response.json() as { cycle: number; event_count: number; events: SimulationEvent[] };
      setChangedCases(new Set(result.events.map((event) => event.case_id).filter((id): id is string => Boolean(id))));
      setLastResult(`Cycle ${result.cycle}: ${result.event_count} persisted event${result.event_count === 1 ? "" : "s"}.`);
      await refresh(); window.setTimeout(() => setChangedCases(new Set()), 5000);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Simulation tick failed."); }
    finally { tickInFlight.current = false; setTicking(false); }
  }, [refresh]);
  useEffect(() => { if (!auto || !data) return; const timer = window.setInterval(() => { if (!tickInFlight.current) void runTick(); }, data.simulation.tick_interval_seconds * 1000); return () => window.clearInterval(timer); }, [auto, data, runTick]);
  useEffect(() => { const timer = window.setInterval(() => { if (!tickInFlight.current) void refresh().catch(() => undefined); }, 30000); return () => window.clearInterval(timer); }, [refresh]);
  const queue = useMemo<PriorityCase[]>(() => {
    if (!data) return [];
    const customers = new Map(data.customers.map((customer) => [customer.id, customer]));
    return data.cases.map((item) => { const customer = customers.get(item.customer_id); const invoice = item.evaluation.invoice; const promises = item.evaluation.promises; return { id: item.case_id, customerId: item.customer_id, customerName: item.customer_name, customerReference: customer?.account_reference ?? "Recovery account", amount: money(invoice?.outstanding_amount ?? customer?.outstanding_amount ?? "0"), state: item.evaluation.derived_state, daysOverdue: invoice?.days_overdue ?? 0, promiseSignal: promises.some((promise) => promise.state === "ACTIVE") ? "Active promise" : promises.some((promise) => promise.state === "BROKEN") ? "Promise broken" : "No active promise", allowed: item.evaluation.eligibility.allowed, reason: item.evaluation.eligibility.allowed ? "Recovery eligible" : item.evaluation.eligibility.blocking_reasons.join(" · ").replaceAll("_", " ") }; });
  }, [data]);
  const names = useMemo(() => new Map(data?.customers.map((customer) => [customer.id, customer.name]) ?? []), [data?.customers]);
  const latestPayment = data?.events[0]?.metadata.payment_amount;
  return <main className="min-h-screen overflow-x-hidden"><div className="w-full bg-fuchsia-500 px-4 py-5 text-center text-2xl font-black tracking-[0.18em] text-black sm:text-4xl">RENDER VERIFICATION ACTIVE</div><AppHeader simulationDate={data?.simulation.simulation_date ?? data?.portfolio.simulation_date} connected={Boolean(data)} /><div className="mx-auto max-w-[1580px] px-6 py-12 lg:px-10 lg:py-14">
    {!data && !error && <div className="h-[540px] animate-pulse border border-white/[.06] bg-white/[.025]" />}
    {error && <p className="border border-rose-300/20 bg-rose-300/[.06] p-5 text-sm text-rose-200">{error}</p>}
    {data && <><section className="flex flex-col justify-between gap-9 pb-12 lg:flex-row lg:items-end"><div className="max-w-3xl"><p className="text-[11px] font-bold uppercase tracking-[.22em] text-sky-300">Operations command center</p><h1 className="mt-5 text-4xl font-semibold tracking-[-.055em] text-white sm:text-5xl">Portfolio Recovery</h1><p className="mt-5 max-w-2xl text-base leading-7 text-slate-400">{data.portfolio.total_customers} active B2B accounts · {data.portfolio.total_invoices} receivables · a factual recovery position driven by the virtual operating date.</p></div><div className="w-full max-w-md"><SimulationControl cycle={data.simulation.cycle} interval={data.simulation.tick_interval_seconds} busy={ticking} auto={auto} lastResult={lastResult} onAutoChange={setAuto} onTick={() => void runTick()} /></div></section>
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5"><PortfolioMetricCard label="Total outstanding" value={money(data.portfolio.total_outstanding_amount)} detail="Across open receivables" impact={latestPayment ? `↓ ${money(latestPayment)} recovered in latest cycle` : undefined} tone="blue" /><PortfolioMetricCard label="Overdue exposure" value={money(data.recovery.overdue_exposure)} detail="Past-due factual exposure" tone="red" /><PortfolioMetricCard label="Recovered this cycle" value={latestPayment ? money(latestPayment) : "—"} detail="Latest persisted payment event" tone="green" /><PortfolioMetricCard label="Promise risk" value={money(data.recovery.broken_promise_exposure)} detail="Exposure behind missed commitments" tone="amber" /><PortfolioMetricCard label="Attention required" value={String(data.recovery.cases_requiring_attention ?? data.recovery.cases_eligible_for_recovery)} detail="Cases requiring factual review" tone="red" /></section>
      <section className="mt-12 grid gap-7 xl:grid-cols-[minmax(0,2.05fr)_minmax(340px,.95fr)]"><PriorityQueue items={queue} onSelect={setSelected} changedCaseIds={changedCases} /><aside className="space-y-5"><PortfolioSignals signals={data.recovery} /><LiveEventFeed events={data.events} customers={names} /><IntelligenceBoundary /></aside></section><InvoiceRegister invoices={data.invoices} customerNames={names} />
    </>}</div>{selected && <CaseWorkspace item={selected} onClose={() => setSelected(null)} liveVersion={data?.simulation.cycle ?? 0} affected={changedCases.has(selected.id)} />}</main>;
}
