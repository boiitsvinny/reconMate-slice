import { cx } from "./ui";

type Tone = "blue" | "red" | "amber" | "green";

export function PortfolioMetricCard({ label, value, detail, impact, state, tone = "blue", emphasis = false, className }: { label: string; value: string; detail: string; impact?: string; state?: string; tone?: Tone; emphasis?: boolean; className?: string }) {
  const tones: Record<Tone, string> = {
    blue: "border-sky-300/14 text-sky-300",
    red: "border-rose-300/14 text-rose-300",
    amber: "border-amber-300/14 text-amber-200",
    green: "border-emerald-300/14 text-emerald-300",
  };

  return (
    <article className={cx("group relative min-h-[144px] overflow-hidden rounded-2xl border bg-[#08111f]/95 p-5 shadow-[0_14px_36px_rgba(0,0,0,.16)] transition duration-300 hover:-translate-y-0.5", emphasis && "border-current/30 shadow-[0_18px_44px_rgba(0,0,0,.28)]", tones[tone], className)}>
      <div className="absolute inset-x-0 top-0 h-px bg-current opacity-30" />
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11px] font-bold uppercase tracking-[0.15em] text-slate-300">{label}</p>
        {state && <span className="rounded-full border border-current/20 bg-current/[.04] px-2 py-0.5 text-[9px] font-bold uppercase tracking-[.1em] opacity-80">{state}</span>}
      </div>
      <p className={cx("mt-3 font-semibold tracking-[-0.04em] text-white", emphasis ? "text-3xl" : "text-[28px]")}>{value}</p>
      <p className="mt-2 text-[13px] leading-5 text-slate-400">{detail}</p>
      {impact && <p className="mt-2 text-xs font-semibold text-emerald-300">{impact}</p>}
    </article>
  );
}
