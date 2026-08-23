import { Panel, SectionHeader, StatusPill } from "./ui";

export function IntelligenceBoundary() {
  return (
    <Panel>
      <SectionHeader eyebrow="Communication intelligence" title="Bounded by factual control" />
      <div className="p-5 pt-0">
        <p className="text-xs leading-5 text-slate-400">
          AI interprets customer communications. Payments, disputes, recovery state and workflow execution remain deterministic and operator controlled.
        </p>
        <div className="mt-4 grid grid-cols-3 gap-2 text-center">
          <StatusPill tone="slate">Signals</StatusPill>
          <StatusPill tone="sky">Recommend</StatusPill>
          <StatusPill tone="slate">Approve</StatusPill>
        </div>
      </div>
    </Panel>
  );
}
