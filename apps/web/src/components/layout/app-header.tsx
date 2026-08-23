type AppHeaderProps = {
  simulationDate?: string | null;
  connected: boolean;
};

export function AppHeader({ simulationDate, connected }: AppHeaderProps) {
  return (
    <header className="flex items-center justify-between gap-4 border-b border-white/[0.07] bg-[#09111e]/95 px-4 py-3 sm:px-6 lg:px-10">
      <div className="flex min-w-0 items-center gap-3">
        <div className="grid h-8 w-8 shrink-0 place-items-center border border-sky-300/15 bg-sky-400/[.08]">
          <span className="text-xs font-semibold text-sky-300">R</span>
        </div>
        <div className="min-w-0">
          <div className="text-[15px] font-semibold tracking-[-0.02em] text-white">ReconMate</div>
          <div className="truncate text-[10px] font-medium uppercase tracking-[0.16em] text-slate-500">Recovery operations</div>
        </div>
      </div>
      <div className="hidden flex-1 pl-8 text-[11px] font-semibold uppercase tracking-[.16em] text-slate-500 lg:block">Portfolio command center</div>
      <div className="flex items-center gap-3">
        <div className="hidden border border-emerald-300/15 bg-emerald-300/[0.06] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.13em] text-emerald-200 sm:block">System optimal</div>
        <div className="border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-right">
          <div className="text-[10px] font-medium uppercase tracking-[0.12em] text-slate-500">Simulation date</div>
          <div className="mt-0.5 text-xs font-semibold text-slate-200">{simulationDate ?? "-"}</div>
        </div>
        <span className={`h-2 w-2 ${connected ? "bg-emerald-400 shadow-[0_0_10px_rgba(74,222,128,.8)]" : "bg-rose-400"}`} aria-label={connected ? "API connected" : "API unavailable"} />
      </div>
    </header>
  );
}
