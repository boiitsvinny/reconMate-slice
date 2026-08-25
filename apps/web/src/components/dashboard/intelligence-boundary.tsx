import { Panel, SectionHeader, StatusPill } from "./ui";

export function IntelligenceBoundary() {
  return (
    <Panel>
      <SectionHeader eyebrow="Controlled operations" title="Decision guardrails" detail="How recommendations are reviewed and acted on" prominent />
      <div className="p-5 pt-0">
        <p className="text-xs leading-5 text-slate-400">
          Recommendations combine factual recovery conditions with interpreted communication signals. They never change payments, disputes, case state, or execute workflows automatically.
        </p>
        <div className="mt-4 grid grid-cols-3 gap-2 text-center">
          <StatusPill tone="slate">Interpret</StatusPill>
          <StatusPill tone="sky">Recommend</StatusPill>
          <StatusPill tone="emerald">Operator acts</StatusPill>
        </div>
      </div>
    </Panel>
  );
}
