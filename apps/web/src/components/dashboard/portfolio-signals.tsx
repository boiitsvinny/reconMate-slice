import { Panel, SectionHeader } from "./ui";

type Signals = { cases_awaiting_payment: number; cases_blocked_by_dispute: number; escalated_cases: number };

export function PortfolioSignals({ signals, totalCases }: { signals: Signals; totalCases: number }) {
  const items = [
    ["Escalated cases", signals.escalated_cases, "Broken or severe conditions", "bg-rose-400"],
    ["Disputes on hold", signals.cases_blocked_by_dispute, "Recovery automation blocked", "bg-amber-300"],
    ["Promise monitoring", signals.cases_awaiting_payment, "Recorded payment commitments", "bg-sky-400"],
  ] as const;

  return (
    <Panel>
      <SectionHeader eyebrow="Risk and opportunity" title="Operational load" detail={`Share of ${totalCases} recovery cases`} />
      <div className="space-y-5 p-5">
        {items.map(([label, value, detail, dot]) => (
          <div key={label}>
            <div className="flex items-baseline justify-between gap-3">
              <div className="flex items-center gap-2"><span className={`h-1.5 w-1.5 ${dot}`} /><p className="text-xs font-medium text-slate-200">{label}</p></div>
              <p className="text-base font-semibold tabular-nums text-white">{value}</p>
            </div>
            <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/[.055]"><div className={`h-full rounded-full ${dot}`} style={{ width: `${totalCases > 0 ? Math.min(100, (value / totalCases) * 100) : 0}%` }} /></div>
            <div className="mt-1.5 flex justify-between gap-3 text-[10px] text-slate-500"><span>{detail}</span><span>{totalCases > 0 ? `${Math.round((value / totalCases) * 100)}%` : "0%"}</span></div>
          </div>
        ))}
        <p className="border-t border-white/[.06] pt-3 text-[10px] leading-4 text-slate-600">Signals can overlap when a case has more than one factual condition.</p>
      </div>
    </Panel>
  );
}
