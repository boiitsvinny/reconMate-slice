"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

type AppHeaderProps = { connected: boolean; updating?: boolean };

const navigation = [
  ["/", "Home"],
  ["/history", "History"],
  ["/analytics", "Analytics"],
  ["/reports", "Reports"],
] as const;

export function AppHeader({ connected, updating = false }: AppHeaderProps) {
  const pathname = usePathname();
  const [today, setToday] = useState("");

  useEffect(() => {
    const update = () => setToday(new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" }).format(new Date()));
    update();
    const timer = window.setInterval(update, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <>
    <header className="sticky top-0 z-40 flex h-16 items-center justify-between gap-3 border-b border-white/[0.09] bg-[#07111f]/95 px-4 shadow-lg shadow-black/10 backdrop-blur-xl sm:px-6 lg:px-10">
      <div className="flex min-w-0 items-center gap-3">
        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-sky-300/20 bg-sky-400/[.1]">
          <span className="text-xs font-semibold text-sky-300">R</span>
        </div>
        <div className="min-w-0">
          <div className="text-[15px] font-semibold tracking-[-0.02em] text-white">ReconMate</div>
          <div className="truncate text-[10px] font-medium uppercase tracking-[0.16em] text-slate-500">Recovery operations</div>
        </div>
      </div>
      <nav aria-label="Primary navigation" className="hidden items-center gap-1 rounded-xl border border-white/[.07] bg-white/[.025] p-1 sm:flex lg:ml-6">
        {navigation.map(([href, label]) => {
          const active = href === "/" ? pathname === href : pathname.startsWith(href);
          return <Link aria-current={active ? "page" : undefined} key={href} href={href} className={`rounded-lg px-3.5 py-2 text-[11px] font-semibold transition ${active ? "bg-sky-300 text-slate-950 shadow-sm shadow-sky-400/20" : "text-slate-400 hover:bg-white/[.05] hover:text-white"}`}>{label}</Link>;
        })}
      </nav>
      <div className="flex items-center gap-3">
        <div className="hidden rounded-lg border border-emerald-300/15 bg-emerald-300/[0.06] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.13em] text-emerald-200 lg:block">System optimal</div>
        <div className="hidden rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-right sm:block">
          <div className="text-[10px] font-medium uppercase tracking-[0.12em] text-slate-500">Today</div>
          <div className="mt-0.5 text-xs font-semibold text-slate-200">{today || "-"}</div>
        </div>
        <span className={`h-2 w-2 rounded-full ${updating ? "animate-pulse bg-sky-300" : connected ? "bg-emerald-400 shadow-[0_0_10px_rgba(74,222,128,.8)]" : "bg-rose-400"}`} aria-label={updating ? "Refreshing live data" : connected ? "API connected" : "API unavailable"} />
      </div>
    </header>
    <nav aria-label="Mobile navigation" className="fixed inset-x-0 bottom-0 z-50 border-t border-white/[.09] bg-[#07111f]/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl sm:hidden">
      <div className="grid h-16 grid-cols-4">
        {navigation.map(([href, label]) => {
          const active = href === "/" ? pathname === href : pathname.startsWith(href);
          return (
            <Link aria-current={active ? "page" : undefined} key={href} href={href} className={`relative flex min-w-0 flex-col items-center justify-center gap-1 text-[10px] font-semibold transition active:scale-95 ${active ? "text-sky-300" : "text-slate-500"}`}>
              {active && <span className="absolute inset-x-4 top-0 h-0.5 rounded-full bg-sky-300" />}
              <NavIcon route={href} active={active} />
              <span>{label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
    </>
  );
}

function NavIcon({ route, active }: { route: string; active: boolean }) {
  const paths: Record<string, React.ReactNode> = {
    "/": <path d="M3 10.5 12 3l9 7.5V21a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1V10.5Z" />,
    "/history": <><path d="M4 4h16v16H4z" /><path d="M8 8h8M8 12h8M8 16h5" /></>,
    "/analytics": <><path d="M4 20V10m6 10V4m6 16v-7m4 7H2" /></>,
    "/reports": <><path d="M6 3h9l3 3v15H6z" /><path d="M9 11h6M9 15h6" /></>,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill={active ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{paths[route]}</svg>;
}
