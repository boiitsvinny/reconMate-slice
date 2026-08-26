import type { PortfolioIntelligence } from "@/lib/intelligence-api";
import type { LatestIntelligenceCycle, Recovery } from "./data";
import { Panel, SectionHeader, StatusPill } from "./ui";

type Props = {
  intelligence?: PortfolioIntelligence;
  recovery: Recovery;
  latestCycle: LatestIntelligenceCycle | null;
  approvals: number;
  recoveredThisCycle: string;
  evaluationUpdatedAt: number;
  loading: boolean;
  error: string | null;
  synchronizing: boolean;
};

export function OperationalIntelligenceHero({ intelligence, recovery, latestCycle, approvals, recoveredThisCycle, evaluationUpdatedAt, loading, error, synchronizing }: Props) {
  if (loading) return <Panel className="h-52 animate-pulse bg-white/[.035]"><span className="sr-only">Loading ReconMate intelligence</span></Panel>;

  const holds = intelligence?.customers.filter((item) => item.recommendation.action === "MONITOR" || item.recommendation.action === "WAIT_FOR_PROMISE").length ?? 0;
  const activeCases = recovery.active_cases ?? recovery.total_cases;
  const evaluatedAt = evaluationUpdatedAt ? new Date(evaluationUpdatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "not yet available";
  const activity = synchronizing
    ? "Reassessing the portfolio against new operational facts…"
    : latestCycle
      ? `Latest reassessment: cycle ${latestCycle.cycle} · ${latestCycle.event_count} factual event${latestCycle.event_count === 1 ? "" : "s"}`
      : "Current portfolio evaluation is complete";

  return (
    <Panel className="overflow-hidden border-sky-300/15">
      <SectionHeader
        eyebrow="Decision system activity"
        title="ReconMate Intelligence"
        detail="Current evidence is continuously reassessed before recovery work is recommended."
        prominent
        action={<StatusPill tone={synchronizing ? "sky" : "emerald"}>{synchronizing ? "Reassessing" : "Evaluation current"}</StatusPill>}
      />
      <div className="grid grid-cols-2 gap-px bg-white/[.06] sm:grid-cols-3 xl:grid-cols-6">
        <IntelligenceMetric label="Cases monitored" value={String(activeCases)} detail="Active recovery cases" />
        <IntelligenceMetric label="Reassessed this cycle" value={latestCycle ? String(latestCycle.customers_affected) : "—"} detail="Affected customer records" />
        <IntelligenceMetric label="Decisions changed" value={latestCycle ? String(latestCycle.recommendations_changed) : "—"} detail="Material recommendation moves" emphasis={Boolean(latestCycle?.recommendations_changed)} />
        <IntelligenceMetric label="Human approvals" value={String(approvals)} detail="Current controlled actions" />
        <IntelligenceMetric label="Deliberate holds" value={String(holds)} detail="Monitor or wait decisions" restraint />
        <IntelligenceMetric label="Recovered this cycle" value={recoveredThisCycle} detail="Persisted payment events" restraint={recoveredThisCycle !== "—"} />
      </div>
      <div className="flex flex-col gap-2 border-t border-white/[.06] px-5 py-3 text-[11px] sm:flex-row sm:items-center sm:justify-between">
        <p className={synchronizing ? "animate-pulse text-sky-200" : "text-slate-400"}>{activity}</p>
        <p className="text-slate-600">Portfolio evaluation refreshed at {evaluatedAt}{error ? " · refresh delayed" : ""}</p>
      </div>
    </Panel>
  );
}

function IntelligenceMetric({ label, value, detail, emphasis = false, restraint = false }: { label: string; value: string; detail: string; emphasis?: boolean; restraint?: boolean }) {
  return (
    <article className="bg-[#08111f] p-4">
      <p className="text-[9px] font-bold uppercase leading-4 tracking-[.12em] text-slate-500">{label}</p>
      <p className={`mt-2 text-2xl font-semibold tabular-nums ${emphasis ? "text-amber-100" : restraint ? "text-emerald-200" : "text-white"}`}>{value}</p>
      <p className="mt-1 text-[10px] leading-4 text-slate-600">{detail}</p>
    </article>
  );
}
