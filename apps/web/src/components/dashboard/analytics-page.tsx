"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AppHeader } from "@/components/layout/app-header";
import { CaseWorkspace } from "./case-workspace";
import { CaseApi, createPriorityQueue, Customer, fetchJson, PriorityCase, Recommendation } from "./data";
import { IntelligenceBoundary } from "./intelligence-boundary";
import { NextAction } from "./next-action";
import { Panel, SectionHeader, StatusPill, buttonStyles } from "./ui";

const label = (value: string) => value.replaceAll("_", " ");
const priorityTone = (priority: Recommendation["priority"]) => priority === "CRITICAL" ? "rose" : priority === "HIGH" ? "amber" : priority === "MEDIUM" ? "sky" : "slate";

export function AnalyticsPage() {
  const [data, setData] = useState<{ customers: Customer[]; cases: CaseApi[]; recommendations: Recommendation[] } | null>(null);
  const [selected, setSelected] = useState<PriorityCase | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      const [customers, cases, recommendations] = await Promise.all([
        fetchJson<Customer[]>("/customers"), fetchJson<CaseApi[]>("/recovery/cases"), fetchJson<Recommendation[]>("/recovery/recommendations"),
      ]);
      setData({ customers, cases, recommendations });
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load recovery intelligence.");
    }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const queue = useMemo(() => data ? createPriorityQueue(data.customers, data.cases, data.recommendations) : [], [data]);
  const actionable = queue.filter((item) => item.recommendedAction !== "NO_ACTION_REQUIRED");

  return (
    <main className="min-h-screen overflow-x-hidden">
      <AppHeader connected={Boolean(data)} />
      <div className="mx-auto max-w-[1580px] px-4 py-8 sm:px-6 lg:px-10 lg:py-10">
        <header className="max-w-3xl">
          <p className="text-[11px] font-bold uppercase tracking-[.22em] text-sky-200">AI decision center</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-.04em] text-white sm:text-4xl">Recovery Intelligence</h1>
          <p className="mt-3 text-sm leading-6 text-slate-300/80">Prioritized next-best actions and explanations based on live recovery facts and bounded communication intelligence.</p>
        </header>
        {error && <div className="mt-7 rounded-2xl border border-rose-300/20 bg-rose-300/[.07] p-5 text-sm text-rose-100">{error}</div>}
        {!data && !error && <div className="mt-7 h-[560px] animate-pulse rounded-2xl border border-white/[.07] bg-white/[.035]" />}
        {data && (
          <>
            <section className="mt-7 grid gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(320px,.75fr)]">
              <NextAction item={queue[0]} onSelect={setSelected} />
              <IntelligenceBoundary />
            </section>
            <Panel className="mt-7">
              <SectionHeader eyebrow="Recommendation queue" title="Suggested operator actions" detail={`${actionable.length} live suggestions, ordered by backend priority`} />
              <div className="divide-y divide-white/[.055]">
                {actionable.map((item) => (
                  <article key={item.id} className="grid gap-4 p-5 transition hover:bg-white/[.025] md:grid-cols-[minmax(180px,1fr)_minmax(220px,1.4fr)_auto] md:items-center">
                    <div><div className="flex items-center gap-2"><p className="font-medium text-white">{item.customerName}</p><StatusPill tone={priorityTone(item.recommendationPriority)}>{item.recommendationPriority}</StatusPill></div><p className="mt-1 text-xs text-slate-500">{item.amount} / {item.daysOverdue} days overdue</p></div>
                    <div><p className="text-xs font-semibold text-sky-200">{label(item.recommendedAction)}</p><p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-400">{item.recommendationReason}</p></div>
                    <button type="button" onClick={() => setSelected(item)} className={buttonStyles.secondary}>Review</button>
                  </article>
                ))}
                {!actionable.length && <p className="p-10 text-center text-sm text-slate-500">No operator action is currently recommended.</p>}
              </div>
            </Panel>
          </>
        )}
      </div>
      {selected && <CaseWorkspace item={selected} onClose={() => setSelected(null)} liveVersion={0} affected={false} />}
    </main>
  );
}
