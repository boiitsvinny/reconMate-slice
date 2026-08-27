"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useInsightMode } from "@/components/intelligence/insight-mode";

type AppHeaderProps = { connected?: boolean; updating?: boolean };

const navigation = [
  ["/", "HOME"],
  ["/reports", "REPORTS"],
  ["/analytics", "ANALYZE"],
  ["/history", "HISTORY"],
] as const;

export function AppHeader({ connected, updating = false }: AppHeaderProps) {
  const pathname = usePathname();
  const home = pathname === "/";
  const [navigationVisible, setNavigationVisible] = useState(true);
  const lastScrollY = useRef(0);
  const { enabled: inspectionEnabled, toggle: toggleInspection } = useInsightMode();

  useEffect(() => {
    let frame = 0;
    const updateNavigation = () => {
      const current = Math.max(0, window.scrollY);
      const change = current - lastScrollY.current;
      if (current < 72) setNavigationVisible(true);
      else if (Math.abs(change) >= 6) setNavigationVisible(change < 0);
      lastScrollY.current = current;
      frame = 0;
    };
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(updateNavigation);
    };
    lastScrollY.current = window.scrollY;
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, []);

  const systemLabel = connected === undefined ? "Connecting" : updating ? "Synchronizing" : connected ? "System optimal" : "Connection degraded";

  return (
    <>
    <header className={`pointer-events-none sticky top-0 z-40 grid grid-cols-[1fr_auto_1fr] items-center gap-3 px-3 py-1.5 transition-transform duration-300 ease-out sm:px-5 lg:px-7 ${navigationVisible ? "translate-y-0" : "-translate-y-full"}`}>
      <div className="header-glass pointer-events-auto flex w-fit min-w-0 items-center gap-2 rounded-xl p-1 pr-2.5">
        <button type="button" onClick={toggleInspection} aria-label="Toggle Intelligence Inspection" aria-pressed={inspectionEnabled} className="grid h-8 w-8 shrink-0 place-items-center overflow-hidden rounded-lg border border-sky-200/25 bg-slate-950/35 p-0.5 shadow-[0_0_18px_rgba(56,189,248,.1)] transition hover:border-sky-200/45 hover:bg-sky-400/[.08] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300/60">
          <Image src="/reconmate-mark.png" alt="" width={24} height={24} priority className="h-6 w-6 object-contain" />
        </button>
        <Link href="/" aria-label="ReconMate home" className="min-w-0">
        <div className="min-w-0">
          <div className="text-sm font-semibold tracking-[-0.02em] text-white">ReconMate</div>
          <div className="truncate text-[8px] font-semibold uppercase tracking-[0.16em] text-slate-500 sm:text-[9px]">Recovery operations</div>
        </div>
        </Link>
      </div>
      <nav aria-label="Primary navigation" className="header-glass pointer-events-auto hidden items-center gap-1 rounded-2xl p-1 sm:flex">
        {navigation.map(([href, label]) => {
          const active = href === "/" ? pathname === href : pathname.startsWith(href);
          return <Link aria-current={active ? "page" : undefined} key={href} href={href} className={`rounded-lg px-3.5 py-2 text-[11px] font-semibold transition ${active ? "bg-sky-300 text-slate-950 shadow-sm shadow-sky-400/20" : "text-slate-400 hover:bg-white/[.05] hover:text-white"}`}>{label}</Link>;
        })}
      </nav>
      <div className="pointer-events-auto justify-self-end">
        {!home && <div className="header-glass hidden items-center gap-2 rounded-2xl p-1.5 pl-3 lg:flex"><span className={`text-[10px] font-semibold uppercase tracking-[0.13em] ${connected === undefined || updating ? "text-sky-200" : connected ? "text-emerald-200" : "text-amber-100"}`}>{systemLabel}</span><span className={`h-2 w-2 rounded-full ${connected === undefined || updating ? "animate-pulse bg-sky-300" : connected ? "bg-emerald-400 shadow-[0_0_10px_rgba(74,222,128,.8)]" : "bg-rose-400"}`} aria-label={connected === undefined ? "Connecting to API" : updating ? "Refreshing live data" : connected ? "API connected" : "API unavailable"} /></div>}
      </div>
    </header>
    <nav aria-label="Mobile navigation" className={`fixed inset-x-0 bottom-0 z-50 border-t border-white/[.09] bg-[#07111f]/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl transition-transform duration-300 ease-out sm:hidden ${navigationVisible ? "translate-y-0" : "translate-y-full"}`}>
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
