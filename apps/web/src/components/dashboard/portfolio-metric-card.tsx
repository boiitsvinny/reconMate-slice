import { cx } from "./ui";

type Tone = "blue" | "red" | "amber" | "green";

export function PortfolioMetricCard({ label, value, detail, impact, state, tone = "blue", className }: { label: string; value: string; detail: string; impact?: string; state?: string; tone?: Tone; className?: string }) {
  const tones: Record<Tone, string> = {
    blue: "border-sky-300/14 text-sky-300",
    red: "border-rose-300/14 text-rose-300",
    amber: "border-amber-300/14 text-amber-200",
    green: "border-emerald-300/14 text-emerald-300",
  };

  return (
    <article className={cx("group relative min-h-[156px] overflow-hidden rounded-2xl border bg-[#08111f]/95 p-5 shadow-[0_18px_45px_rgba(0,0,0,.18)] transition duration-300 hover:-translate-y-0.5", tones[tone], className)}>
      <div className="absolute inset-x-0 top-0 h-px bg-current opacity-30" />
      <div className="flex items-start justify-between gap-3">
        <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">{label}</p>
        {state && <span className="rounded-full border border-current/20 bg-current/[.04] px-2 py-0.5 text-[9px] font-bold uppercase tracking-[.1em] opacity-80">{state}</span>}
      </div>
      <p className="mt-4 text-2xl font-semibold tracking-[-0.035em] text-white sm:text-3xl">{value}</p>
      <p className="mt-3 text-xs leading-5 text-slate-500">{detail}</p>
      {impact && <p className="mt-2 text-[11px] font-medium text-emerald-300">{impact}</p>}
    </article>
  );
}
