import { Panel, StatusPill } from "./ui";

type Props = {
  totalOutstanding: string;
  overdueExposure: string;
  totalCustomers: number;
  totalInvoices: number;
  attentionCases: number;
  formatMoney: (value: string | number) => string;
};

export function PortfolioHealth({ totalOutstanding, overdueExposure, totalCustomers, totalInvoices, attentionCases, formatMoney }: Props) {
  const outstanding = Number(totalOutstanding);
  const overdue = Number(overdueExposure);
  const overdueShare = outstanding > 0 ? Math.min(100, Math.max(0, (overdue / outstanding) * 100)) : 0;

  return (
    <Panel className="relative overflow-hidden">
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-sky-300/70 via-sky-300/20 to-transparent" />
      <div className="grid gap-8 p-6 sm:p-7 lg:grid-cols-[1fr_1.05fr] lg:gap-10">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-[10px] font-bold uppercase tracking-[.2em] text-sky-300">Portfolio health</p>
            <StatusPill tone={overdueShare >= 50 ? "rose" : overdueShare >= 25 ? "amber" : "emerald"}>{overdueShare.toFixed(0)}% overdue</StatusPill>
          </div>
          <p className="mt-5 text-xs font-medium uppercase tracking-[.13em] text-slate-500">Total outstanding</p>
          <p className="mt-2 text-4xl font-semibold tracking-[-.045em] text-white sm:text-5xl">{formatMoney(totalOutstanding)}</p>
          <p className="mt-4 max-w-sm text-xs leading-5 text-slate-400">Open receivables across {totalCustomers} customer accounts. Portfolio coverage includes {totalInvoices} invoices.</p>
        </div>
        <div className="border-t border-white/[.07] pt-6 lg:border-l lg:border-t-0 lg:pl-8 lg:pt-0">
          <p className="text-[10px] font-bold uppercase tracking-[.16em] text-rose-300">Exposure currently at risk</p>
          <p className="mt-3 text-3xl font-semibold tracking-[-.035em] text-white">{formatMoney(overdueExposure)}</p>
          <p className="mt-2 text-xs text-slate-500">Past due and requiring active recovery oversight</p>
          <div className="mt-6 h-2 overflow-hidden bg-white/[.06]" aria-label={`${overdueShare.toFixed(0)} percent of outstanding exposure is overdue`}>
            <div className="h-full bg-gradient-to-r from-amber-300 to-rose-400" style={{ width: `${overdueShare}%` }} />
          </div>
          <div className="mt-3 flex items-center justify-between gap-4 text-[11px] text-slate-500">
            <span>{overdueShare.toFixed(1)}% of outstanding</span>
            <span className="font-medium text-rose-200">{attentionCases} cases need attention</span>
          </div>
        </div>
      </div>
    </Panel>
  );
}
