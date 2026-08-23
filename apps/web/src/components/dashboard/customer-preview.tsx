import type { PriorityCase } from "./dashboard";

const toneForState = (state: string) => state === "ESCALATED" ? "text-rose-300" : state === "AWAITING_CUSTOMER" ? "text-amber-200" : "text-sky-300";

export function CustomerPreview({ item }: { item: PriorityCase }) {
  return <div className="pointer-events-none absolute right-4 top-[calc(100%-6px)] z-30 hidden w-[290px] rounded-2xl border border-white/[0.12] bg-[#111a2d]/95 p-4 shadow-2xl shadow-black/60 backdrop-blur-2xl lg:block">
    <div className="flex items-start justify-between gap-3">
      <div><p className="text-sm font-semibold text-white">{item.customerName}</p><p className="mt-0.5 text-[10px] uppercase tracking-[0.13em] text-slate-500">Customer intelligence</p></div>
      <span className={`text-[10px] font-bold tracking-[0.12em] ${toneForState(item.state)}`}>{item.state.replaceAll("_", " ")}</span>
    </div>
    <div className="mt-4 grid grid-cols-2 gap-3 border-y border-white/[0.07] py-3">
      <div><p className="text-[10px] uppercase tracking-[0.1em] text-slate-500">Outstanding</p><p className="mt-1 text-base font-semibold text-white">{item.amount}</p></div>
      <div><p className="text-[10px] uppercase tracking-[0.1em] text-slate-500">Eligibility</p><p className={`mt-1 text-sm font-semibold ${item.allowed ? "text-emerald-300" : "text-amber-200"}`}>{item.allowed ? "Eligible" : "Blocked"}</p></div>
    </div>
    <ul className="mt-3 space-y-1.5 text-xs leading-5 text-slate-400">
      <li>{item.daysOverdue > 0 ? `${item.daysOverdue} days overdue` : "Current invoice exposure"}</li>
      <li>{item.promiseSignal}</li>
      <li className={item.allowed ? "text-emerald-300" : "text-amber-200"}>{item.reason}</li>
    </ul>
  </div>;
}
