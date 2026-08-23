import { cx } from "./ui";

type Tone = "blue" | "red" | "amber" | "green";

export function PortfolioMetricCard({ label, value, detail, impact, tone = "blue" }: { label: string; value: string; detail: string; impact?: string; tone?: Tone }) {
  const tones: Record<Tone, string> = {
    blue: "border-sky-300/14 bg-sky-400/[0.035] text-sky-300",
    red: "border-rose-300/14 bg-rose-400/[0.035] text-rose-300",
    amber: "border-amber-300/14 bg-amber-400/[0.035] text-amber-200",
    green: "border-emerald-300/14 bg-emerald-400/[0.035] text-emerald-300",
  };

  return (
    <article className={cx("group relative min-h-[156px] overflow-hidden rounded-2xl border p-5 transition duration-300 hover:-translate-y-0.5", tones[tone])}>
      <div className="absolute inset-x-0 top-0 h-px bg-current opacity-30" />
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">{label}</p>
      <p className="mt-4 text-2xl font-semibold tracking-[-0.035em] text-white sm:text-3xl">{value}</p>
      <p className="mt-3 text-xs leading-5 text-slate-500">{detail}</p>
      {impact && <p className="mt-2 text-[11px] font-medium text-emerald-300">{impact}</p>}
    </article>
  );
}
