"use client";

import { useMemo, useState } from "react";
import { Panel, SectionHeader, StatusPill, cx } from "./ui";

type Invoice = { id: string; invoice_number: string; customer_id: string; due_date: string; outstanding_amount: string; status: string };

const money = (value: string) => {
  const amount = Number(value);
  return amount >= 100000
    ? `INR ${(amount / 100000).toFixed(1)}L`
    : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(amount);
};
const statusTone = (status: string) => status === "PAID" ? "emerald" : status === "DISPUTED" ? "amber" : status === "OVERDUE" ? "rose" : "sky";

export function InvoiceRegister({ invoices, customerNames }: { invoices: Invoice[]; customerNames: Map<string, string> }) {
  const pageSize = 30;
  const [page, setPage] = useState(0);
  const pages = Math.max(1, Math.ceil(invoices.length / pageSize));
  const rows = useMemo(() => invoices.slice(page * pageSize, (page + 1) * pageSize), [invoices, page]);
  const first = invoices.length ? page * pageSize + 1 : 0;
  const last = Math.min((page + 1) * pageSize, invoices.length);

  return (
    <Panel className="mt-7">
      <SectionHeader
        eyebrow="Receivables register"
        title="Invoice operations"
        detail="Live factual invoice records. No simulated client-side rows."
        action={
          <div className="flex items-center gap-3 text-xs text-slate-400">
            <span>{first}-{last} of {invoices.length}</span>
            <button aria-label="Previous invoice page" disabled={page === 0} onClick={() => setPage((value) => value - 1)} className="border border-white/[.08] px-2 py-1 text-sm hover:text-white disabled:opacity-30">Prev</button>
            <button aria-label="Next invoice page" disabled={page >= pages - 1} onClick={() => setPage((value) => value + 1)} className="border border-white/[.08] px-2 py-1 text-sm hover:text-white disabled:opacity-30">Next</button>
          </div>
        }
      />
      <div className="overflow-x-auto">
        <div className="min-w-[850px]">
          <div className="grid grid-cols-[1.25fr_1fr_.75fr_.8fr_.8fr] gap-4 border-b border-white/[.06] px-5 py-3 text-[10px] font-bold uppercase tracking-[.13em] text-slate-600">
            <span>Invoice / account</span>
            <span>Customer</span>
            <span>Due date</span>
            <span>Exposure</span>
            <span>Status</span>
          </div>
          {rows.map((invoice) => (
            <div key={invoice.id} className="grid grid-cols-[1.25fr_1fr_.75fr_.8fr_.8fr] gap-4 border-b border-white/[.045] px-5 py-3 text-sm transition last:border-b-0 hover:bg-sky-400/[.03]">
              <div>
                <p className="font-medium text-slate-200">{invoice.invoice_number}</p>
                <p className="mt-0.5 text-[10px] text-slate-600">{invoice.id.slice(0, 8)}</p>
              </div>
              <p className="truncate text-slate-400">{customerNames.get(invoice.customer_id) ?? "Portfolio account"}</p>
              <p className="text-slate-400">{invoice.due_date}</p>
              <p className="font-semibold tabular-nums text-white">{money(invoice.outstanding_amount)}</p>
              <StatusPill tone={statusTone(invoice.status)}>{invoice.status}</StatusPill>
            </div>
          ))}
          {!rows.length && <p className={cx("px-5 py-10 text-center text-sm text-slate-500")}>No invoices returned by the API.</p>}
        </div>
      </div>
    </Panel>
  );
}
