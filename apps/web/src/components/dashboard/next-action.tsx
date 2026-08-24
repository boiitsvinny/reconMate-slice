import type { PriorityCase } from "./data";
import { buttonStyles, cx, Panel, SectionEyebrow, StatusPill } from "./ui";

const label = (value: string) => value.replaceAll("_", " ");
const priorityTone = (priority: PriorityCase["recommendationPriority"]) => priority === "CRITICAL" ? "rose" : priority === "HIGH" ? "amber" : priority === "MEDIUM" ? "sky" : "slate";

export function NextAction({ item, onSelect }: { item?: PriorityCase; onSelect: (item: PriorityCase) => void }) {
  return (
    <Panel className="flex min-h-[258px] flex-col border-sky-300/15">
      <div className="flex items-center justify-between gap-3 border-b border-white/[.07] px-5 py-4">
        <div>
          <SectionEyebrow>Recommended next action</SectionEyebrow>
          <p className="mt-2 text-xs text-slate-500">Highest-priority live recommendation</p>
        </div>
        {item && <StatusPill tone={priorityTone(item.recommendationPriority)}>{item.recommendationPriority}</StatusPill>}
      </div>
      {item ? (
        <div className="flex flex-1 flex-col p-5">
          <h2 className="text-xl font-semibold tracking-[-.025em] text-white">{label(item.recommendedAction)}</h2>
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400">
            <span className="font-medium text-slate-200">{item.customerName}</span>
            <span>{item.amount}</span>
            <span>{item.daysOverdue > 0 ? `${item.daysOverdue} days overdue` : item.state.replaceAll("_", " ")}</span>
          </div>
          <p className="mt-4 line-clamp-3 text-xs leading-5 text-slate-400">{item.recommendationReason}</p>
          <div className="mt-auto flex flex-col items-stretch justify-between gap-4 pt-5 sm:flex-row sm:items-end">
            <p className="text-[10px] uppercase tracking-[.11em] text-slate-500">{item.humanApprovalRequired ? "Human approval required" : "Operator review"}</p>
            <button type="button" onClick={() => onSelect(item)} className={cx(buttonStyles.primary, "shrink-0")}>Review case</button>
          </div>
        </div>
      ) : (
        <div className="grid flex-1 place-items-center p-6 text-center"><p className="text-sm text-slate-500">No recovery recommendation is currently available.</p></div>
      )}
    </Panel>
  );
}
