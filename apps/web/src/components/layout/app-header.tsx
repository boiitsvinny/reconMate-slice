"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

type AppHeaderProps = { connected: boolean };

const navigation = [
  ["/", "Home"],
  ["/history", "History"],
  ["/analytics", "Analytics"],
  ["/reports", "Reports"],
] as const;

export function AppHeader({ connected }: AppHeaderProps) {
  const pathname = usePathname();
  const [today, setToday] = useState("");

  useEffect(() => {
    const update = () => setToday(new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" }).format(new Date()));
    update();
    const timer = window.setInterval(update, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <header className="sticky top-0 z-40 flex flex-wrap items-center justify-between gap-4 border-b border-white/[0.09] bg-[#07111f]/90 px-4 py-3 shadow-lg shadow-black/10 backdrop-blur-xl sm:px-6 lg:flex-nowrap lg:px-10">
      <div className="flex min-w-0 items-center gap-3">
        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-sky-300/20 bg-sky-400/[.1]">
          <span className="text-xs font-semibold text-sky-300">R</span>
        </div>
        <div className="min-w-0">
          <div className="text-[15px] font-semibold tracking-[-0.02em] text-white">ReconMate</div>
          <div className="truncate text-[10px] font-medium uppercase tracking-[0.16em] text-slate-500">Recovery operations</div>
        </div>
      </div>
      <nav aria-label="Primary navigation" className="order-3 flex w-full items-center gap-1 overflow-x-auto rounded-xl border border-white/[.07] bg-white/[.025] p-1 lg:order-none lg:ml-6 lg:w-auto">
        {navigation.map(([href, label]) => {
          const active = href === "/" ? pathname === href : pathname.startsWith(href);
          return <Link key={href} href={href} className={`rounded-lg px-3.5 py-2 text-[11px] font-semibold transition ${active ? "bg-sky-300 text-slate-950 shadow-sm shadow-sky-400/20" : "text-slate-400 hover:bg-white/[.05] hover:text-white"}`}>{label}</Link>;
        })}
      </nav>
      <div className="flex items-center gap-3">
        <div className="hidden rounded-lg border border-emerald-300/15 bg-emerald-300/[0.06] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.13em] text-emerald-200 sm:block">System optimal</div>
        <div className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-right">
          <div className="text-[10px] font-medium uppercase tracking-[0.12em] text-slate-500">Today</div>
          <div className="mt-0.5 text-xs font-semibold text-slate-200">{today || "-"}</div>
        </div>
        <span className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-400 shadow-[0_0_10px_rgba(74,222,128,.8)]" : "bg-rose-400"}`} aria-label={connected ? "API connected" : "API unavailable"} />
      </div>
    </header>
  );
}
