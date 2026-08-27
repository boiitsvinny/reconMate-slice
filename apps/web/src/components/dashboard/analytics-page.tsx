"use client";

import { useState } from "react";
import { AppHeader } from "@/components/layout/app-header";
import { CommandActivityPanel, CommandCenter, CommandNotices } from "@/components/intelligence/command-center";
import { CaseWorkspace } from "./case-workspace";
import { CustomerPreview, useCasePreview } from "./customer-preview";
import { LiveEventFeed } from "./live-event-feed";
import type { PriorityCase } from "./data";
import { useRecoveryQueue, useSimulationEvents } from "./queries";
import { buttonStyles } from "./ui";

export function AnalyticsPage() {
  const [selected, setSelected] = useState<PriorityCase | null>(null);
  const { preview, openPreview, closePreview } = useCasePreview();
  const { customers, cases, recommendations, currentIntelligence, queue } = useRecoveryQueue();
  const events = useSimulationEvents();
  const queries = [customers, cases, recommendations, currentIntelligence, events];
  const ready = queries.every((query) => Boolean(query.data));
  const error = queries.find((query) => query.isError)?.error;
  const errorMessage = error instanceof Error ? error.message : error ? "Unable to load recovery intelligence." : null;
  const updating = ready && queries.some((query) => query.isFetching);
  const retry = () => Promise.all(queries.map((query) => query.refetch()));
  const customerNames = new Map((customers.data ?? []).map((customer) => [customer.id, customer.name]));
  const openCommandTarget = (targetType: string, targetId: string) => {
    const match = targetType === "CUSTOMER"
      ? queue.find((item) => item.customerId === targetId)
      : queue.find((item) => item.id === targetId);
    if (!match) return false;
    openPreview(match);
    return true;
  };
  const openCustomerWorkspace = (customerId: string) => {
    const match = queue.find((item) => item.customerId === customerId);
    if (!match) return false;
    setSelected(match);
    return true;
  };

  return (
    <main className="workspace-analyze min-h-screen overflow-x-hidden">
      <AppHeader connected={!ready && !errorMessage ? undefined : ready && !errorMessage} updating={updating && !errorMessage} />
      <div className="mx-auto max-w-[1580px] px-4 py-6 pb-24 sm:px-6 sm:py-8 sm:pb-10 lg:px-10 lg:py-10">
        <header className="max-w-3xl">
          <p className="text-[11px] font-bold uppercase tracking-[.22em] text-sky-200">Intelligence investigation workbench</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-.04em] text-white sm:text-4xl">Analyze ReconMate Decisions</h1>
          <p className="mt-3 text-sm leading-6 text-slate-300/80">Ask a grounded operational question, inspect what matched, compare returned accounts, and verify the facts behind each score and recommendation.</p>
        </header>
        <CommandCenter customers={customers.data ?? []} queue={queue} onOpenTarget={openCommandTarget} onOpenWorkspace={openCustomerWorkspace} />
        {!ready && errorMessage && <div className="mt-7 flex flex-col justify-between gap-4 rounded-2xl border border-rose-300/20 bg-rose-300/[.07] p-5 sm:flex-row sm:items-center"><p className="text-sm text-rose-100">{errorMessage}</p><button type="button" onClick={() => void retry()} className="rounded-lg border border-rose-200/25 px-3 py-2 text-xs font-bold text-rose-50">Try again</button></div>}
        {!ready && !errorMessage && <div className="mt-7 h-[560px] animate-pulse rounded-2xl border border-white/[.07] bg-white/[.035]" />}
        {ready && errorMessage && <div className="mt-5 flex flex-col justify-between gap-3 rounded-xl border border-amber-300/15 bg-amber-300/[.06] px-4 py-3 sm:flex-row sm:items-center"><p className="text-xs text-amber-100">Live refresh is delayed. Showing the last successful recommendations.</p><button type="button" onClick={() => void retry()} className="text-xs font-semibold text-amber-50 underline decoration-amber-200/30 underline-offset-4">Retry refresh</button></div>}
        {ready && <>
          <section className="mt-7 grid gap-7 xl:grid-cols-2" aria-label="Recent operational evidence and command activity">
            <LiveEventFeed events={events.data ?? []} customers={customerNames} onOpenCase={(caseId) => {
              const match = queue.find((item) => item.id === caseId);
              if (!match) return false;
              openPreview(match);
              return true;
            }} />
            <CommandActivityPanel />
          </section>
          <CommandNotices />
        </>}
      </div>
      <CustomerPreview preview={preview} onClose={closePreview} onViewMore={(item) => { closePreview(); setSelected(item); }} />
      {selected && <CaseWorkspace item={selected} onClose={() => setSelected(null)} liveVersion={0} affected={false} />}
    </main>
  );
}
