"use client";

import { useState } from "react";
import { AppHeader } from "@/components/layout/app-header";
import { CommandActivityPanel, CommandCenter } from "@/components/intelligence/command-center";
import { PortfolioIntelligenceSnapshot } from "@/components/intelligence/portfolio-intelligence-snapshot";
import { CaseWorkspace } from "./case-workspace";
import { CustomerPreview, useCasePreview } from "./customer-preview";
import { PriorityCase, Recommendation } from "./data";
import { IntelligenceBoundary } from "./intelligence-boundary";
import { useInsightMode } from "@/components/intelligence/insight-mode";
import { NextAction } from "./next-action";
import { useRecoveryQueue } from "./queries";
import { Panel, SectionHeader, StatusPill, buttonStyles } from "./ui";

const label = (value: string) => value.replaceAll("_", " ");
const priorityTone = (priority: Recommendation["priority"]) => priority === "CRITICAL" ? "rose" : priority === "HIGH" ? "amber" : priority === "MEDIUM" ? "sky" : "slate";
const queueState = (action: string) => action === "ESCALATE_TO_HUMAN" ? "Decision required" : action === "HOLD_FOR_DISPUTE" ? "Review required" : action === "MONITOR_ACTIVE_PROMISE" ? "Waiting / blocked" : action === "NO_ACTION_REQUIRED" ? "Monitoring" : "Follow-up recommended";

export function AnalyticsPage() {
  const { enabled: inspectionEnabled } = useInsightMode();
  const [selected, setSelected] = useState<PriorityCase | null>(null);
  const { preview, openPreview, closePreview } = useCasePreview();
  const { customers, cases, recommendations, queue } = useRecoveryQueue();
  const queries = [customers, cases, recommendations];
  const ready = queries.every((query) => Boolean(query.data));
  const error = queries.find((query) => query.isError)?.error;
  const errorMessage = error instanceof Error ? error.message : error ? "Unable to load recovery intelligence." : null;
  const updating = ready && queries.some((query) => query.isFetching);
  const retry = () => Promise.all(queries.map((query) => query.refetch()));
  const actionable = queue.filter((item) => item.recommendedAction !== "NO_ACTION_REQUIRED");
  const openCommandTarget = (targetType: string, targetId: string) => {
    const match = targetType === "CUSTOMER"
      ? queue.find((item) => item.customerId === targetId)
      : queue.find((item) => item.id === targetId);
    if (!match) return false;
    openPreview(match);
    return true;
  };

  return (
    <main className="min-h-screen overflow-x-hidden">
      <AppHeader connected={ready && !errorMessage} updating={updating && !errorMessage} />
      <div className="mx-auto max-w-[1580px] px-4 py-6 pb-24 sm:px-6 sm:py-8 sm:pb-10 lg:px-10 lg:py-10">
        <header className="max-w-3xl">
          <p className="text-[11px] font-bold uppercase tracking-[.22em] text-sky-200">AI decision center</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-.04em] text-white sm:text-4xl">Recovery Intelligence</h1>
          <p className="mt-3 text-sm leading-6 text-slate-300/80">Prioritized next-best actions and explanations based on live recovery facts and bounded communication intelligence.</p>
        </header>
        <CommandCenter onOpenTarget={openCommandTarget} />
        {!ready && errorMessage && <div className="mt-7 flex flex-col justify-between gap-4 rounded-2xl border border-rose-300/20 bg-rose-300/[.07] p-5 sm:flex-row sm:items-center"><p className="text-sm text-rose-100">{errorMessage}</p><button type="button" onClick={() => void retry()} className="rounded-lg border border-rose-200/25 px-3 py-2 text-xs font-bold text-rose-50">Try again</button></div>}
        {!ready && !errorMessage && <div className="mt-7 h-[560px] animate-pulse rounded-2xl border border-white/[.07] bg-white/[.035]" />}
        {ready && errorMessage && <div className="mt-5 flex flex-col justify-between gap-3 rounded-xl border border-amber-300/15 bg-amber-300/[.06] px-4 py-3 sm:flex-row sm:items-center"><p className="text-xs text-amber-100">Live refresh is delayed. Showing the last successful recommendations.</p><button type="button" onClick={() => void retry()} className="text-xs font-semibold text-amber-50 underline decoration-amber-200/30 underline-offset-4">Retry refresh</button></div>}
        {ready && (
          <>
            <section className="mt-7 grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,.85fr)]" aria-label="Current operational context">
              <NextAction item={queue[0]} onSelect={openPreview} />
              <PortfolioIntelligenceSnapshot />
            </section>
            <section className="mt-7"><CommandActivityPanel /></section>
            <Panel className="mt-7 overflow-hidden">
              <SectionHeader eyebrow="Ongoing operational work" title="Recommended queue" detail={`${actionable.length} live recommendations, ordered by backend priority`} prominent />
              <div className="operational-scrollbar max-h-[34rem] divide-y divide-white/[.055] overflow-y-auto overscroll-contain" role="region" aria-label="Recommended operator queue" tabIndex={0}>
                {actionable.map((item) => (
                  <article key={item.id} className="grid gap-4 p-4 transition active:scale-[.99] sm:p-5 md:grid-cols-[minmax(180px,1fr)_minmax(220px,1.4fr)_auto] md:items-center md:hover:bg-white/[.025]">
                    <div><div className="flex flex-wrap items-center gap-2"><p className="font-medium text-white">{item.customerName}</p><StatusPill tone={priorityTone(item.recommendationPriority)}>{item.recommendationPriority}</StatusPill><StatusPill tone={item.recommendedAction === "ESCALATE_TO_HUMAN" ? "rose" : item.recommendedAction === "HOLD_FOR_DISPUTE" ? "amber" : "sky"}>{queueState(item.recommendedAction)}</StatusPill></div><p className="mt-1 text-xs text-slate-500">{item.amount} / {item.daysOverdue} days overdue</p></div>
                    <div><p className="text-xs font-semibold text-sky-200">{label(item.recommendedAction)}</p><p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-400">{item.recommendationReason}</p></div>
                    <button type="button" onClick={() => openPreview(item)} className={`${buttonStyles.primary} w-full md:w-auto`}>Preview case</button>
                  </article>
                ))}
                {!actionable.length && <p className="p-10 text-center text-sm text-slate-500">No operator action is currently recommended.</p>}
              </div>
            </Panel>
            {inspectionEnabled && <section className="mt-7"><IntelligenceBoundary /></section>}
          </>
        )}
      </div>
      <CustomerPreview preview={preview} onClose={closePreview} onViewMore={(item) => { closePreview(); setSelected(item); }} />
      {selected && <CaseWorkspace item={selected} onClose={() => setSelected(null)} liveVersion={0} affected={false} />}
    </main>
  );
}
