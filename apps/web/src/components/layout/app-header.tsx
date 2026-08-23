type AppHeaderProps = {
  simulationDate?: string | null;
  connected: boolean;
};

export function AppHeader({ simulationDate, connected }: AppHeaderProps) {
  return (
    <header className="flex items-center justify-between gap-4 border-b border-white/[0.07] bg-[#09111e] px-5 py-3 sm:px-8 lg:px-10">
      <div className="flex items-center gap-3">
        <div className="grid h-7 w-7 place-items-center bg-sky-400/15">
          <span className="text-xs font-semibold text-sky-300">R</span>
        </div>
        <div>
          <div className="text-[15px] font-semibold tracking-[-0.02em] text-white">ReconMate</div>
          <div className="text-[10px] font-medium uppercase tracking-[0.16em] text-slate-500">Recovery operations</div>
        </div>
      </div>
      <nav className="hidden flex-1 items-center gap-6 pl-8 text-[11px] font-medium text-slate-500 lg:flex"><span>Dashboard</span><span className="border-b-2 border-sky-400 pb-3 text-sky-300">Portfolio</span><span>Analytics</span><span>Reports</span></nav>
      <div className="flex items-center gap-3">
        <div className="hidden border border-emerald-300/15 bg-emerald-300/[0.06] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.13em] text-emerald-200 sm:block">System optimal</div>
        <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-right">
          <div className="text-[10px] font-medium uppercase tracking-[0.12em] text-slate-500">Simulation date</div>
          <div className="mt-0.5 text-xs font-semibold text-slate-200">{simulationDate ?? "—"}</div>
        </div>
        <span className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-400 shadow-[0_0_10px_rgba(74,222,128,.8)]" : "bg-rose-400"}`} aria-label={connected ? "API connected" : "API unavailable"} />
      </div>
    </header>
  );
}
