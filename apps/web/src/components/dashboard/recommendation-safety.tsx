import { Panel, SectionHeader, StatusPill } from "./ui";

type Props = {
  activeDisputes: number;
  activePromises: number;
};

export function RecommendationSafety({ activeDisputes, activePromises }: Props) {
  return (
    <Panel className="mt-7 overflow-hidden">
      <SectionHeader
        eyebrow="Controlled decision support"
        title="Decision guardrails"
        detail="ReconMate explains and prepares recovery work; operators remain responsible for consequential actions."
        prominent
      />
      <div className="grid gap-px bg-white/[.06] sm:grid-cols-2 xl:grid-cols-4">
        <Guardrail step="01" title="Interpret signals" detail="Reads factual recovery conditions and bounded communication signals." tone="slate" />
        <Guardrail step="02" title="Recommend next work" detail="Produces an explainable action based on the current operational state." tone="sky" />
        <Guardrail step="03" title="Respect blockers" detail={`${activeDisputes} dispute-blocked and ${activePromises} promise-monitoring case${activePromises === 1 ? "" : "s"} currently constrain aggressive recovery.`} tone="amber" />
        <Guardrail step="04" title="Operator confirms" detail="No payment, dispute, customer communication, or unsafe workflow is changed silently." tone="emerald" />
      </div>
    </Panel>
  );
}

function Guardrail({ step, title, detail, tone }: { step: string; title: string; detail: string; tone: "slate" | "sky" | "amber" | "emerald" }) {
  return (
    <article className="bg-[#08111f] p-4 sm:p-5">
      <div className="flex items-center justify-between gap-3"><span className="text-[10px] font-semibold tabular-nums text-slate-600">{step}</span><StatusPill tone={tone}>{title}</StatusPill></div>
      <p className="mt-3 text-xs leading-5 text-slate-400">{detail}</p>
    </article>
  );
}
