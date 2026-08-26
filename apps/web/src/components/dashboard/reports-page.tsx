"use client";

import { useState } from "react";
import { AppHeader } from "@/components/layout/app-header";
import { CaseWorkspace } from "./case-workspace";
import { CustomerPreview, useCasePreview } from "./customer-preview";
import type { PriorityCase } from "./data";
import {
  useLatestIntelligenceCycle,
  usePaymentRequests,
  usePortfolioIntelligence,
  useRecovery,
  useRecoveryActions,
  useRecoveryQueue,
  useSimulationEvents,
} from "./queries";
import { RecoveryEvidenceReport } from "./reports-sections";

export function ReportsPage() {
  const [selected, setSelected] = useState<PriorityCase | null>(null);
  const { preview, openPreview, closePreview } = useCasePreview();
  const { customers, cases, recommendations, queue } = useRecoveryQueue();
  const recovery = useRecovery();
  const intelligence = usePortfolioIntelligence();
  const latestCycle = useLatestIntelligenceCycle();
  const events = useSimulationEvents();
  const actions = useRecoveryActions();
  const paymentRequests = usePaymentRequests();
  const requiredQueries = [customers, cases, recommendations, recovery, intelligence, latestCycle, events, actions];
  const queries = [...requiredQueries, paymentRequests];
  const ready = requiredQueries.every((query) => query.data !== undefined);
  const error = requiredQueries.find((query) => query.isError)?.error;
  const errorMessage = error instanceof Error ? error.message : error ? "Unable to load the recovery evidence report." : null;
  const providerEvidenceUnavailable = paymentRequests.isError;
  const updating = ready && queries.some((query) => query.isFetching);
  const retry = () => Promise.all(queries.map((query) => query.refetch()));
  const selectedTransition = selected
    ? latestCycle.data?.transitions.find((transition) => transition.entity_type === "RECOVERY_CASE" && transition.entity_id === selected.id)
    : undefined;

  return (
    <main className="workspace-reports min-h-screen overflow-x-hidden">
      <AppHeader connected={ready && !errorMessage} updating={updating && !errorMessage} />
      <div className="mx-auto max-w-[1580px] px-4 py-6 pb-24 sm:px-6 sm:py-8 sm:pb-10 lg:px-10 lg:py-10">
        <header className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
          <div className="max-w-3xl">
            <p className="text-[11px] font-bold uppercase tracking-[.22em] text-sky-200">Recovery evidence report</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-[-.04em] text-white sm:text-4xl">Portfolio Recovery Report</h1>
            <p className="mt-3 text-sm leading-6 text-slate-300/80">A decision and outcome record of the current portfolio: what changed, how ReconMate responded, where operators acted, and what remains unresolved.</p>
          </div>
        </header>

        {!ready && errorMessage && <div className="mt-7 flex flex-col justify-between gap-4 rounded-2xl border border-rose-300/20 bg-rose-300/[.07] p-5 sm:flex-row sm:items-center"><p className="text-sm text-rose-100">{errorMessage}</p><button type="button" onClick={() => void retry()} className="rounded-lg border border-rose-200/25 px-3 py-2 text-xs font-bold text-rose-50">Try again</button></div>}
        {!ready && !errorMessage && <div className="mt-7 h-[660px] animate-pulse rounded-2xl border border-white/[.07] bg-white/[.035]" />}
        {ready && errorMessage && <div className="mt-5 flex flex-col justify-between gap-3 rounded-xl border border-amber-300/15 bg-amber-300/[.06] px-4 py-3 sm:flex-row sm:items-center"><p className="text-xs text-amber-100">Live refresh is delayed. Showing the last successful report data.</p><button type="button" onClick={() => void retry()} className="text-xs font-semibold text-amber-50 underline decoration-amber-200/30 underline-offset-4">Retry refresh</button></div>}
        {ready && providerEvidenceUnavailable && <div className="mt-5 flex flex-col justify-between gap-3 rounded-xl border border-amber-300/15 bg-amber-300/[.06] px-4 py-3 sm:flex-row sm:items-center"><p className="text-xs text-amber-100">Payment-provider evidence is temporarily unavailable. The rest of the live recovery report is still current.</p><button type="button" onClick={() => void paymentRequests.refetch()} className="text-xs font-semibold text-amber-50 underline decoration-amber-200/30 underline-offset-4">Retry provider evidence</button></div>}
        {ready && recovery.data && intelligence.data && latestCycle.data !== undefined && events.data && actions.data && (
          <section className="mt-7 print:mt-4">
            <RecoveryEvidenceReport
              recovery={recovery.data}
              intelligence={intelligence.data}
              latestCycle={latestCycle.data}
              events={events.data}
              queue={queue}
              actions={actions.data}
              paymentRequests={paymentRequests.data ?? []}
              onSelectCase={openPreview}
            />
          </section>
        )}
      </div>
      <CustomerPreview preview={preview} onClose={closePreview} onViewMore={(item) => { closePreview(); setSelected(item); }} />
      {selected && <CaseWorkspace item={selected} onClose={() => setSelected(null)} liveVersion={latestCycle.data?.cycle ?? 0} affected={Boolean(selectedTransition)} transition={selectedTransition} />}
    </main>
  );
}
