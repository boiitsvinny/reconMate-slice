"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Panel, SectionHeader, StatusPill, cx } from "./ui";

type Invoice = { id: string; invoice_number: string; customer_id: string; due_date: string; outstanding_amount: string; status: string };
type CustomerSummary = { name: string; account_reference: string; outstanding_amount: string };
type Preview = { invoiceId: string; x: number; y: number };

const money = (value: string) => {
  const amount = Number(value);
  return amount >= 100000
    ? `INR ${(amount / 100000).toFixed(1)}L`
    : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(amount);
};
const statusTone = (status: string) => status === "PAID" ? "emerald" : status === "DISPUTED" ? "amber" : status === "OVERDUE" ? "rose" : "sky";

export function InvoiceRegister({ invoices, customers }: { invoices: Invoice[]; customers: Map<string, CustomerSummary> }) {
  const pageSize = 30;
  const [page, setPage] = useState(0);
  const pages = Math.max(1, Math.ceil(invoices.length / pageSize));
  const rows = useMemo(() => invoices.slice(page * pageSize, (page + 1) * pageSize), [invoices, page]);
  const first = invoices.length ? page * pageSize + 1 : 0;
  const last = Math.min((page + 1) * pageSize, invoices.length);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewVisible, setPreviewVisible] = useState(false);
  const closeTimer = useRef<number | null>(null);

  const cancelClose = () => {
    if (closeTimer.current !== null) window.clearTimeout(closeTimer.current);
    closeTimer.current = null;
  };
  const closePreview = (delay = 500) => {
    cancelClose();
    closeTimer.current = window.setTimeout(() => {
      setPreviewVisible(false);
      closeTimer.current = window.setTimeout(() => setPreview(null), 180);
    }, delay);
  };
  const openPreview = (invoice: Invoice, clientX: number, clientY: number) => {
    cancelClose();
    setPreview({ invoiceId: invoice.id, x: Math.min(clientX + 14, window.innerWidth - 340), y: Math.min(clientY + 14, window.innerHeight - 280) });
    setPreviewVisible(true);
    if (window.matchMedia("(hover: hover)").matches) closePreview(1100);
  };

  useEffect(() => () => cancelClose(), []);
  const previewInvoice = preview ? invoices.find((invoice) => invoice.id === preview.invoiceId) : null;

  return (
    <Panel className="mt-7">
      <SectionHeader
        eyebrow="Receivables register"
        title="Invoice operations"
        detail="Live factual invoice records. No simulated client-side rows."
        action={
          <div className="flex items-center gap-3 text-xs text-slate-400">
            <span>{first}-{last} of {invoices.length}</span>
            <button aria-label="Previous invoice page" disabled={page === 0} onClick={() => setPage((value) => value - 1)} className="rounded-lg border border-white/[.08] px-2 py-1 text-sm hover:text-white disabled:opacity-30">Prev</button>
            <button aria-label="Next invoice page" disabled={page >= pages - 1} onClick={() => setPage((value) => value + 1)} className="rounded-lg border border-white/[.08] px-2 py-1 text-sm hover:text-white disabled:opacity-30">Next</button>
          </div>
        }
      />
      <div className="divide-y divide-white/[.055] md:hidden">
        {rows.map((invoice) => (
          <button type="button" key={invoice.id} onClick={(event) => openPreview(invoice, event.clientX, event.clientY)} className="flex w-full items-start justify-between gap-4 p-4 text-left transition active:bg-sky-400/[.07]">
            <div className="min-w-0"><p className="truncate text-sm font-semibold text-white">{invoice.invoice_number}</p><p className="mt-1 truncate text-xs text-slate-400">{customers.get(invoice.customer_id)?.name ?? "Portfolio account"}</p><p className="mt-2 text-[11px] text-slate-500">Due {invoice.due_date}</p></div>
            <div className="flex shrink-0 flex-col items-end gap-2"><p className="text-sm font-semibold tabular-nums text-white">{money(invoice.outstanding_amount)}</p><StatusPill tone={statusTone(invoice.status)}>{invoice.status}</StatusPill></div>
          </button>
        ))}
        {!rows.length && <p className="px-5 py-10 text-center text-sm text-slate-500">No invoices returned by the API.</p>}
      </div>
      <div className="hidden overflow-x-auto md:block">
        <div className="min-w-[850px]">
          <div className="grid grid-cols-[1.25fr_1fr_.75fr_.8fr_.8fr] gap-4 border-b border-white/[.06] px-5 py-3 text-[10px] font-bold uppercase tracking-[.13em] text-slate-600">
            <span>Invoice / account</span>
            <span>Customer</span>
            <span>Due date</span>
            <span>Exposure</span>
            <span>Status</span>
          </div>
          {rows.map((invoice) => (
            <button type="button" key={invoice.id} onClick={(event) => openPreview(invoice, event.clientX, event.clientY)} className="grid w-full grid-cols-[1.25fr_1fr_.75fr_.8fr_.8fr] gap-4 border-b border-white/[.045] px-5 py-3 text-left text-sm transition last:border-b-0 hover:bg-sky-400/[.06] focus:bg-sky-400/[.06] focus:outline-none">
              <div>
                <p className="font-medium text-slate-200">{invoice.invoice_number}</p>
                <p className="mt-0.5 text-[10px] text-slate-600">{invoice.id.slice(0, 8)}</p>
              </div>
              <p className="truncate text-slate-400">{customers.get(invoice.customer_id)?.name ?? "Portfolio account"}</p>
              <p className="text-slate-400">{invoice.due_date}</p>
              <p className="font-semibold tabular-nums text-white">{money(invoice.outstanding_amount)}</p>
              <StatusPill tone={statusTone(invoice.status)}>{invoice.status}</StatusPill>
            </button>
          ))}
          {!rows.length && <p className={cx("px-5 py-10 text-center text-sm text-slate-500")}>No invoices returned by the API.</p>}
        </div>
      </div>
      {preview && previewInvoice && (
        <aside
          role="dialog"
          aria-label={`${previewInvoice.invoice_number} invoice profile`}
          onMouseEnter={cancelClose}
          onMouseLeave={() => closePreview(300)}
          className={cx("fixed z-50 w-[320px] rounded-2xl border border-sky-200/20 bg-[#0b1728]/95 p-5 shadow-2xl shadow-black/60 backdrop-blur-xl transition duration-200 max-sm:!bottom-20 max-sm:!left-3 max-sm:!right-3 max-sm:!top-auto max-sm:!w-auto", previewVisible ? "translate-y-0 opacity-100" : "translate-y-1 opacity-0")}
          style={{ left: Math.max(12, preview.x), top: Math.max(12, preview.y) }}
        >
          <div className="flex items-start justify-between gap-4">
            <div><p className="text-[10px] font-bold uppercase tracking-[.16em] text-sky-300">Invoice profile</p><h3 className="mt-1 text-base font-semibold text-white">{previewInvoice.invoice_number}</h3></div>
            <div className="flex items-center gap-2"><StatusPill tone={statusTone(previewInvoice.status)}>{previewInvoice.status}</StatusPill><button type="button" onClick={() => closePreview(0)} aria-label="Close invoice profile" className="grid h-7 w-7 place-items-center rounded-full border border-white/10 text-sm text-slate-400 hover:text-white">×</button></div>
          </div>
          <div className="mt-4 rounded-xl border border-white/[.07] bg-white/[.03] p-4">
            <p className="text-xs font-semibold text-slate-200">{customers.get(previewInvoice.customer_id)?.name ?? "Portfolio account"}</p>
            <p className="mt-1 text-[10px] uppercase tracking-[.12em] text-slate-500">{customers.get(previewInvoice.customer_id)?.account_reference ?? "Account reference unavailable"}</p>
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-4 text-xs">
            <div><dt className="text-[10px] uppercase tracking-[.1em] text-slate-500">Invoice exposure</dt><dd className="mt-1 font-semibold text-white">{money(previewInvoice.outstanding_amount)}</dd></div>
            <div><dt className="text-[10px] uppercase tracking-[.1em] text-slate-500">Due date</dt><dd className="mt-1 font-semibold text-white">{previewInvoice.due_date}</dd></div>
            <div className="col-span-2"><dt className="text-[10px] uppercase tracking-[.1em] text-slate-500">Account outstanding</dt><dd className="mt-1 font-semibold text-white">{money(customers.get(previewInvoice.customer_id)?.outstanding_amount ?? "0")}</dd></div>
          </dl>
          <p className="mt-4 text-[10px] leading-4 text-slate-500">Move onto this card to keep it open. Move away and it will fade automatically.</p>
        </aside>
      )}
    </Panel>
  );
}
