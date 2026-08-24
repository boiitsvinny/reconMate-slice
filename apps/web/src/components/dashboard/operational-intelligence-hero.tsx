import type { PortfolioIntelligence } from "@/lib/intelligence-api";
import { Panel, SectionEyebrow, StatusPill } from "./ui";

type Props = {
  intelligence?: PortfolioIntelligence;
  loading: boolean;
  error: string | null;
  overdueExposure: string;
  totalOutstanding: string;
  formatMoney: (value: string | number) => string;
  synchronizing: boolean;
  synchronizedCycle?: number;
};

export function OperationalIntelligenceHero({ intelligence, loading, error, overdueExposure, totalOutstanding, formatMoney, synchronizing, synchronizedCycle }: Props) {
  if (loading) {
    return (
      <Panel className="relative overflow-hidden" >
        <div className="grid animate-pulse gap-8 p-6 sm:p-7 lg:grid-cols-[1.1fr_.9fr]">
          <div className="space-y-4"><div className="h-3 w-48 rounded bg-white/[.07]" /><div className="h-8 w-full max-w-lg rounded bg-white/[.07]" /><div className="h-4 w-3/4 rounded bg-white/[.04]" /></div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3"><div className="h-20 rounded-xl bg-white/[.04]" /><div className="h-20 rounded-xl bg-white/[.04]" /><div className="h-20 rounded-xl bg-white/[.04]" /></div>
        </div>
      </Panel>
    );
  }

  if (!intelligence) {
    return (
      <Panel className="border-amber-300/15 p-6 sm:p-7">
        <SectionEyebrow>Portfolio position</SectionEyebrow>
        <h2 className="mt-3 text-2xl font-semibold tracking-[-.03em] text-white">{formatMoney(overdueExposure)} is currently overdue</h2>
        <p className="mt-2 text-sm leading-6 text-slate-400">Live intelligence is temporarily unavailable. Factual exposure remains visible while the next intelligence refresh is attempted.</p>
        {error && <p className="mt-4 text-xs text-amber-100/75">{error}</p>}
      </Panel>
    );
  }

  const critical = intelligence.level_counts.CRITICAL;
  const high = intelligence.level_counts.HIGH;
  const needsAttention = critical + high;
  const brokenPromises = intelligence.customers.reduce((sum, item) => sum + item.metrics.broken_promise_count, 0);
  const activeDisputes = intelligence.customers.reduce((sum, item) => sum + item.metrics.active_dispute_count, 0);
  const activeRecovery = intelligence.customers.reduce((sum, item) => sum + item.metrics.active_recovery_case_count, 0);
  const headline = critical
    ? `${critical} critical account${critical === 1 ? "" : "s"} require immediate oversight`
    : high
      ? `${high} high-risk account${high === 1 ? "" : "s"} need operator attention`
      : "No high-risk portfolio conditions require immediate action";
  const statusTone = critical ? "rose" : high ? "amber" : "emerald";

  return (
    <Panel className="relative overflow-hidden border-sky-300/15">
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-sky-300/70 via-sky-300/20 to-transparent" />
      <div className="grid gap-7 p-6 sm:p-7 lg:grid-cols-[minmax(0,1.05fr)_minmax(500px,.95fr)] lg:items-center">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <SectionEyebrow>Live portfolio intelligence</SectionEyebrow>
            <StatusPill tone={statusTone}>{critical ? "Critical attention" : high ? "Elevated attention" : "Stable"}</StatusPill>
          </div>
          <h2 className="mt-4 max-w-2xl text-2xl font-semibold tracking-[-.035em] text-white sm:text-3xl">{headline}</h2>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">
            {formatMoney(overdueExposure)} overdue from {formatMoney(totalOutstanding)} outstanding. ReconMate evaluated {intelligence.customer_count} accounts using current recovery facts.
          </p>
          <p className="mt-3 text-[11px] text-slate-600">Evaluated for {intelligence.calculated_at} / average portfolio score {intelligence.average_score}</p>
          {synchronizing && <p className="mt-2 animate-pulse text-[11px] font-medium text-sky-200">Re-evaluating intelligence against the new simulation facts...</p>}
          {!synchronizing && synchronizedCycle !== undefined && <p className="live-enter mt-2 text-[11px] font-medium text-emerald-200">Intelligence synchronized with cycle {synchronizedCycle}.</p>}
          {error && <p className="mt-2 text-[11px] text-amber-200/75">Live refresh is delayed; showing the last successful intelligence evaluation.</p>}
        </div>
        <div aria-label="Attention breakdown" className="grid grid-cols-2 overflow-hidden rounded-2xl border border-white/[.07] bg-black/10 sm:grid-cols-3 xl:grid-cols-6">
          <AttentionMetric label="Critical" value={critical} tone="text-rose-200" />
          <AttentionMetric label="High risk" value={high} tone="text-amber-100" />
          <AttentionMetric label="Needs attention" value={needsAttention} tone="text-sky-200" />
          <AttentionMetric label="Broken promises" value={brokenPromises} tone="text-rose-200" />
          <AttentionMetric label="Active disputes" value={activeDisputes} tone="text-amber-100" />
          <AttentionMetric label="Active recovery" value={activeRecovery} tone="text-emerald-200" />
        </div>
      </div>
    </Panel>
  );
}

function AttentionMetric({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="min-w-0 border-b border-r border-white/[.055] p-3.5 last:border-r-0 sm:p-4">
      <p className="min-h-7 text-[9px] font-semibold uppercase leading-3.5 tracking-[.1em] text-slate-500">{label}</p>
      <p className={`mt-2 text-2xl font-semibold tabular-nums ${tone}`}>{value}</p>
    </div>
  );
}
