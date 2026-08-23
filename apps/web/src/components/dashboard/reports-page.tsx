"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AppHeader } from "@/components/layout/app-header";
import { CaseWorkspace } from "./case-workspace";
import { CaseApi, createPriorityQueue, Customer, fetchJson, PriorityCase, Recommendation, Recovery } from "./data";
import { PortfolioSignals } from "./portfolio-signals";
import { PriorityQueue } from "./priority-queue";

export function ReportsPage() {
  const [data, setData] = useState<{ customers: Customer[]; cases: CaseApi[]; recommendations: Recommendation[]; recovery: Recovery } | null>(null);
  const [selected, setSelected] = useState<PriorityCase | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      const [customers, cases, recommendations, recovery] = await Promise.all([
        fetchJson<Customer[]>("/customers"), fetchJson<CaseApi[]>("/recovery/cases"), fetchJson<Recommendation[]>("/recovery/recommendations"), fetchJson<Recovery>("/recovery/portfolio/summary"),
      ]);
      setData({ customers, cases, recommendations, recovery });
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load recovery reports.");
    }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const queue = useMemo(() => data ? createPriorityQueue(data.customers, data.cases, data.recommendations) : [], [data]);

  return (
    <main className="min-h-screen overflow-x-hidden">
      <AppHeader connected={Boolean(data)} />
      <div className="mx-auto max-w-[1580px] px-4 py-8 sm:px-6 lg:px-10 lg:py-10">
        <header className="max-w-3xl">
          <p className="text-[11px] font-bold uppercase tracking-[.22em] text-sky-200">Recovery reports</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-.04em] text-white sm:text-4xl">Priority Recovery Work</h1>
          <p className="mt-3 text-sm leading-6 text-slate-300/80">Review the complete recovery queue, ordered by the backend recommendation engine. Open a case to approve or execute its existing workflow.</p>
        </header>
        {error && <div className="mt-7 rounded-2xl border border-rose-300/20 bg-rose-300/[.07] p-5 text-sm text-rose-100">{error}</div>}
        {!data && !error && <div className="mt-7 h-[560px] animate-pulse rounded-2xl border border-white/[.07] bg-white/[.035]" />}
        {data && (
          <section className="mt-7 grid gap-7 xl:grid-cols-[minmax(0,2fr)_minmax(320px,.8fr)]">
            <PriorityQueue items={queue} onSelect={setSelected} changedCaseIds={new Set()} />
            <aside><PortfolioSignals signals={data.recovery} totalCases={data.recovery.total_cases} /></aside>
          </section>
        )}
      </div>
      {selected && <CaseWorkspace item={selected} onClose={() => setSelected(null)} liveVersion={0} affected={false} />}
    </main>
  );
}
