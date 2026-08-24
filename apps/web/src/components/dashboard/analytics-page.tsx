"use client";

import { useState } from "react";
import { AppHeader } from "@/components/layout/app-header";
import { CommandCenter } from "@/components/intelligence/command-center";
import { PortfolioIntelligenceSnapshot } from "@/components/intelligence/portfolio-intelligence-snapshot";
import { CaseWorkspace } from "./case-workspace";
import { formatMoney, PriorityCase, Recommendation } from "./data";
import { IntelligenceBoundary } from "./intelligence-boundary";
import { NextAction } from "./next-action";
import { PortfolioMetricCard } from "./portfolio-metric-card";
import { usePortfolio, useRecovery, useRecoveryQueue } from "./queries";
import { Panel, SectionHeader, StatusPill, buttonStyles } from "./ui";

const label = (value: string) => value.replaceAll("_", " ");
const priorityTone = (priority: Recommendation["priority"]) => priority === "CRITICAL" ? "rose" : priority === "HIGH" ? "amber" : priority === "MEDIUM" ? "sky" : "slate";

export function AnalyticsPage() {
  const [selected, setSelected] = useState<PriorityCase | null>(null);
  const { customers, cases, recommendations, queue } = useRecoveryQueue();
  const portfolio = usePortfolio();
  const recovery = useRecovery();
  const queries = [customers, cases, recommendations, portfolio, recovery];
  const ready = queries.every((query) => Boolean(query.data));
  const error = queries.find((query) => query.isError)?.error;
  const errorMessage = error instanceof Error ? error.message : error ? "Unable to load recovery intelligence." : null;
  const updating = ready && queries.some((query) => query.isFetching);
  const actionable = queue.filter((item) => item.recommendedAction !== "NO_ACTION_REQUIRED");
  const openCommandTarget = (targetType: string, targetId: string) => {
    const match = targetType === "CUSTOMER"
      ? queue.find((item) => item.customerId === targetId)
      : queue.find((item) => item.id === targetId);
    if (!match) return false;
    setSelected(match);
    return true;
  };

  return (
    <main className="min-h-screen overflow-x-hidden">
      <AppHeader connected={ready} updating={updating} />
      <div className="mx-auto max-w-[1580px] px-4 py-6 pb-24 sm:px-6 sm:py-8 sm:pb-10 lg:px-10 lg:py-10">
        <header className="max-w-3xl">
          <p className="text-[11px] font-bold uppercase tracking-[.22em] text-sky-200">AI decision center</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-.04em] text-white sm:text-4xl">Recovery Intelligence</h1>
          <p className="mt-3 text-sm leading-6 text-slate-300/80">Prioritized next-best actions and explanations based on live recovery facts and bounded communication intelligence.</p>
        </header>
        <CommandCenter onOpenTarget={openCommandTarget} />
        {!ready && errorMessage && <div className="mt-7 rounded-2xl border border-rose-300/20 bg-rose-300/[.07] p-5 text-sm text-rose-100">{errorMessage}</div>}
        {!ready && !errorMessage && <div className="mt-7 h-[560px] animate-pulse rounded-2xl border border-white/[.07] bg-white/[.035]" />}
        {ready && errorMessage && <p className="mt-5 rounded-xl border border-amber-300/15 bg-amber-300/[.06] px-4 py-3 text-xs text-amber-100">Live refresh is delayed. Showing cached recommendations.</p>}
        {ready && (
          <>
            <section className="mt-7"><PortfolioIntelligenceSnapshot /></section>
            <section className="mt-7 grid gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(320px,.75fr)]">
              <NextAction item={queue[0]} onSelect={setSelected} />
              <IntelligenceBoundary />
            </section>
            {portfolio.data && recovery.data && (
              <section className="mt-7">
                <p className="mb-3 px-1 text-[10px] font-bold uppercase tracking-[.16em] text-slate-400">Portfolio overview</p>
                <div className="hide-scrollbar flex snap-x snap-mandatory gap-4 overflow-x-auto pb-2 sm:grid sm:grid-cols-3 sm:overflow-visible sm:pb-0">
                  <PortfolioMetricCard className="min-w-[78vw] snap-start sm:min-w-0" label="Total exposure" value={formatMoney(portfolio.data.total_outstanding_amount)} detail="Current outstanding receivables" tone="blue" />
                  <PortfolioMetricCard className="min-w-[78vw] snap-start sm:min-w-0" label="Overdue exposure" value={formatMoney(recovery.data.overdue_exposure)} detail="Past-due factual exposure" tone="red" />
                  <PortfolioMetricCard className="min-w-[78vw] snap-start sm:min-w-0" label="Attention required" value={String(recovery.data.cases_requiring_attention ?? recovery.data.cases_eligible_for_recovery)} detail="Cases with an active attention condition" tone="amber" />
                </div>
              </section>
            )}
            <Panel className="mt-7">
              <SectionHeader eyebrow="Recommendation queue" title="Suggested operator actions" detail={`${actionable.length} live suggestions, ordered by backend priority`} />
              <div className="divide-y divide-white/[.055]">
                {actionable.map((item) => (
                  <article key={item.id} className="grid gap-4 p-4 transition active:scale-[.99] sm:p-5 md:grid-cols-[minmax(180px,1fr)_minmax(220px,1.4fr)_auto] md:items-center md:hover:bg-white/[.025]">
                    <div><div className="flex items-center gap-2"><p className="font-medium text-white">{item.customerName}</p><StatusPill tone={priorityTone(item.recommendationPriority)}>{item.recommendationPriority}</StatusPill></div><p className="mt-1 text-xs text-slate-500">{item.amount} / {item.daysOverdue} days overdue</p></div>
                    <div><p className="text-xs font-semibold text-sky-200">{label(item.recommendedAction)}</p><p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-400">{item.recommendationReason}</p></div>
                    <button type="button" onClick={() => setSelected(item)} className={`${buttonStyles.secondary} w-full md:w-auto`}>Review</button>
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
