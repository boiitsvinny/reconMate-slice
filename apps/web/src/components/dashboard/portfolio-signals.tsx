import { Panel, SectionHeader } from "./ui";

type Signals = { cases_awaiting_payment: number; cases_blocked_by_dispute: number; escalated_cases: number };

export function PortfolioSignals({ signals }: { signals: Signals }) {
  const items = [
    ["Promise monitoring", signals.cases_awaiting_payment, "Recorded payment commitments", "bg-sky-400"],
    ["Disputes on hold", signals.cases_blocked_by_dispute, "Recovery automation blocked", "bg-amber-300"],
    ["Escalated cases", signals.escalated_cases, "Broken or severe conditions", "bg-rose-400"],
  ] as const;

  return (
    <Panel>
      <SectionHeader eyebrow="Portfolio signals" title="Current recovery posture" />
      <div className="space-y-4 p-5">
        {items.map(([label, value, detail, dot]) => (
          <div key={label} className="flex items-start gap-3">
            <span className={`mt-1.5 h-2 w-2 ${dot}`} />
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-3">
                <p className="text-xs font-medium text-slate-200">{label}</p>
                <p className="text-lg font-semibold tabular-nums text-white">{value}</p>
              </div>
              <p className="mt-1 text-[11px] text-slate-500">{detail}</p>
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}
