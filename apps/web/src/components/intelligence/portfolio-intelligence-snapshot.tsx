"use client";

import { usePortfolioIntelligence } from "@/components/dashboard/queries";
import { Panel, SectionHeader } from "@/components/dashboard/ui";

export function PortfolioIntelligenceSnapshot({ compact = false }: { compact?: boolean }) {
  const query = usePortfolioIntelligence();
  const data = query.data;
  const error = query.error instanceof Error ? query.error.message : null;
  const activeRecovery = data?.customers.reduce((sum, item) => sum + item.metrics.active_recovery_case_count, 0) ?? 0;
  const attention = data ? data.level_counts.CRITICAL + data.level_counts.HIGH : 0;

  return (
    <Panel>
      <SectionHeader eyebrow="Portfolio intelligence" title="Live operational risk" detail={data ? `${data.customer_count} accounts evaluated / average score ${data.average_score}` : "Loading current intelligence evaluation"} prominent />
      {!data && !error && <div className="h-28 animate-pulse bg-white/[.025]" role="status"><span className="sr-only">Loading portfolio intelligence</span></div>}
      {!data && error && <p className="p-5 text-xs leading-5 text-rose-200">{error}</p>}
      {data && (
        <div className={`grid ${compact ? "grid-cols-2" : "grid-cols-2 sm:grid-cols-4"}`}>
          <SnapshotMetric label="Critical" value={data.level_counts.CRITICAL} tone="text-rose-200" />
          <SnapshotMetric label="High" value={data.level_counts.HIGH} tone="text-amber-100" />
          <SnapshotMetric label="Needs attention" value={attention} tone="text-sky-200" />
          <SnapshotMetric label="Active recovery" value={activeRecovery} tone="text-emerald-200" />
        </div>
      )}
    </Panel>
  );
}

function SnapshotMetric({ label, value, tone }: { label: string; value: number; tone: string }) {
  return <div className="border-r border-t border-white/[.055] p-4 last:border-r-0"><p className="text-[10px] uppercase tracking-[.12em] text-slate-600">{label}</p><p className={`mt-2 text-2xl font-semibold ${tone}`}>{value}</p></div>;
}
