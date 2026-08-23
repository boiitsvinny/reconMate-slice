import type { PriorityCase } from "./dashboard";
import { StatusPill } from "./ui";

const toneForState = (state: string) => state === "ESCALATED" ? "rose" : state === "AWAITING_CUSTOMER" ? "amber" : "sky";

export function CustomerPreview({ item }: { item: PriorityCase }) {
  return (
    <div className="pointer-events-none absolute right-4 top-[calc(100%-6px)] z-30 hidden w-[290px] border border-white/[0.12] bg-[#111a2d]/95 p-4 shadow-2xl shadow-black/60 backdrop-blur-2xl lg:block">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-white">{item.customerName}</p>
          <p className="mt-0.5 text-[10px] uppercase tracking-[0.13em] text-slate-500">Customer intelligence</p>
        </div>
        <StatusPill tone={toneForState(item.state)}>{item.state.replaceAll("_", " ")}</StatusPill>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 border-y border-white/[0.07] py-3">
        <div>
          <p className="text-[10px] uppercase tracking-[0.1em] text-slate-500">Outstanding</p>
          <p className="mt-1 text-base font-semibold text-white">{item.amount}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-[0.1em] text-slate-500">Eligibility</p>
          <p className={`mt-1 text-sm font-semibold ${item.allowed ? "text-emerald-300" : "text-amber-200"}`}>{item.allowed ? "Eligible" : "Blocked"}</p>
        </div>
      </div>
      <ul className="mt-3 space-y-1.5 text-xs leading-5 text-slate-400">
        <li className="font-medium text-sky-200">Next: {item.recommendedAction.replaceAll("_", " ")}</li>
        <li>{item.daysOverdue > 0 ? `${item.daysOverdue} days overdue` : "Current invoice exposure"}</li>
        <li>{item.promiseSignal}</li>
        <li className={item.allowed ? "text-emerald-300" : "text-amber-200"}>{item.reason}</li>
      </ul>
    </div>
  );
}
