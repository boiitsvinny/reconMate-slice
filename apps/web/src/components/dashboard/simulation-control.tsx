"use client";

import { useEffect, useState } from "react";
import { buttonStyles, cx } from "./ui";

type Props = { cycle: number; interval: number; busy: boolean; auto: boolean; lastResult: string; onAutoChange: (enabled: boolean) => void; onTick: () => void };

export function SimulationControl({ cycle, interval, busy, auto, lastResult, onAutoChange, onTick }: Props) {
  const [remaining, setRemaining] = useState(interval);

  useEffect(() => {
    setRemaining(interval);
  }, [cycle, interval, auto]);

  useEffect(() => {
    if (!auto || busy) return;
    const timer = window.setInterval(() => setRemaining((value) => value > 0 ? value - 1 : interval), 1000);
    return () => window.clearInterval(timer);
  }, [auto, busy, interval]);

  return (
    <section className="relative overflow-hidden border border-sky-300/20 bg-slate-950/45 p-4 shadow-[0_18px_45px_rgba(0,0,0,.18)]">
      <div className="absolute inset-y-0 left-0 w-1 bg-sky-400" />
      <div className="flex flex-wrap items-center justify-between gap-4 pl-2">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[.18em] text-sky-300">
            <span className={cx("mr-2 inline-block h-1.5 w-1.5", auto ? "animate-pulse bg-emerald-400" : "bg-slate-500")} />
            Simulation {auto ? "live" : "paused"}
          </p>
          <p className="mt-1 text-xs text-slate-400">
            Cycle <span className="font-semibold text-white">{cycle}</span> / {interval}s interval
          </p>
        </div>
        <div className="border-l border-white/[.08] pl-4 text-right">
          <p className="text-xl font-semibold tabular-nums text-white">{auto ? `${remaining}s` : "-"}</p>
          <p className="text-[10px] uppercase tracking-[.12em] text-slate-500">next cycle</p>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2 pl-2">
        <button disabled={busy} onClick={() => onAutoChange(!auto)} className={buttonStyles.secondary}>{auto ? "Pause" : "Start / Resume"}</button>
        <button disabled={busy} onClick={onTick} className={buttonStyles.primary}>{busy ? "Applying..." : "Run now"}</button>
      </div>
      {lastResult && <p className="mt-3 pl-2 text-[11px] leading-5 text-slate-500">{lastResult}</p>}
    </section>
  );
}
