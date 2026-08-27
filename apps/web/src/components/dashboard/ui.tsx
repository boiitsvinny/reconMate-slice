import type { ReactNode } from "react";

export function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section className={cx("workspace-panel rounded-2xl border border-white/[.09] bg-[#08111f]/95 shadow-[0_18px_45px_rgba(0,0,0,.22)]", className)}>
      {children}
    </section>
  );
}

export function SectionEyebrow({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={cx("flex items-center gap-2.5", className)}>
      <span className="h-4 w-1 shrink-0 rounded-full bg-sky-300 shadow-[0_0_12px_rgba(125,211,252,.55)]" aria-hidden="true" />
      <p className="text-[11px] font-extrabold uppercase leading-none tracking-[.14em] text-sky-200 sm:text-xs">{children}</p>
    </div>
  );
}

export function SectionHeader({
  eyebrow,
  title,
  detail,
  action,
  prominent = false,
}: {
  eyebrow: string;
  title: string;
  detail?: string;
  action?: ReactNode;
  prominent?: boolean;
}) {
  return (
    <div className="flex flex-col items-start justify-between gap-4 border-b border-white/[.07] p-4 sm:flex-row sm:items-end sm:p-5">
      <div className="min-w-0">
        <SectionEyebrow>{eyebrow}</SectionEyebrow>
        <h2 className={cx("mt-2 font-semibold tracking-[-.025em] text-white", prominent ? "text-xl sm:text-2xl" : "text-base")}>{title}</h2>
        {detail && <p className="mt-2 max-w-4xl text-[13px] leading-5 text-slate-400">{detail}</p>}
      </div>
      {action}
    </div>
  );
}

export function StatusPill({ children, tone = "sky" }: { children: ReactNode; tone?: "sky" | "rose" | "amber" | "emerald" | "slate" }) {
  const tones = {
    sky: "border-sky-300/20 bg-sky-400/[.08] text-sky-200",
    rose: "border-rose-300/20 bg-rose-400/[.08] text-rose-200",
    amber: "border-amber-300/20 bg-amber-300/[.08] text-amber-100",
    emerald: "border-emerald-300/20 bg-emerald-400/[.08] text-emerald-200",
    slate: "border-white/[.08] bg-white/[.04] text-slate-300",
  };

  return (
    <span className={cx("inline-flex w-fit items-center rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-[.08em] transition-colors duration-200", tones[tone])}>
      {children}
    </span>
  );
}

export const buttonStyles = {
  primary: "rounded-lg bg-sky-300 px-3.5 py-2 text-xs font-bold text-slate-950 transition duration-150 hover:bg-sky-200 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-45 disabled:active:translate-y-0",
  secondary: "rounded-lg border border-white/10 bg-white/[.03] px-3.5 py-2 text-xs font-semibold text-slate-200 transition duration-150 hover:border-sky-300/35 hover:text-white active:translate-y-px disabled:cursor-not-allowed disabled:opacity-45 disabled:active:translate-y-0",
  danger: "rounded-lg border border-rose-300/25 bg-rose-400/[.06] px-3 py-1.5 text-xs font-bold text-rose-100 transition duration-150 hover:border-rose-200/45 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-45 disabled:active:translate-y-0",
  warning: "rounded-lg border border-amber-300/25 bg-amber-300/[.06] px-3 py-1.5 text-xs font-bold text-amber-100 transition duration-150 hover:border-amber-200/45 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-45 disabled:active:translate-y-0",
  success: "rounded-lg bg-emerald-300 px-3 py-1.5 text-xs font-bold text-emerald-950 transition duration-150 hover:bg-emerald-200 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-45 disabled:active:translate-y-0",
};
