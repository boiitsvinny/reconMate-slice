"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { PriorityLevel } from "@/lib/intelligence-api";
import type { Invoice } from "./data";
import { Panel, SectionHeader, StatusPill, cx } from "./ui";

type CustomerSummary = { name: string; account_reference: string; outstanding_amount: string };
type Preview = { invoiceId: string; x: number; y: number };
type Risk = { level: PriorityLevel; score: number };
type SortKey = "newest" | "oldest" | "risk" | "invoice" | "customer" | "due" | "exposure" | "status";
type StatusFilter = "all" | "pending" | "overdue" | "disputed";

const money = (value: string) => {
  const amount = Number(value);
  return amount >= 100000
    ? `INR ${(amount / 100000).toFixed(1)}L`
    : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(amount);
};
const statusTone = (status: string) => status === "PAID" ? "emerald" : status === "DISPUTED" ? "amber" : status === "OVERDUE" ? "rose" : "sky";
const riskTone = (level?: PriorityLevel) => level === "CRITICAL" ? "rose" : level === "HIGH" ? "amber" : level === "MEDIUM" ? "sky" : "slate";
const riskRank: Record<PriorityLevel, number> = { LOW: 1, MEDIUM: 2, HIGH: 3, CRITICAL: 4 };

export function InvoiceRegister({ invoices, customers, riskByCustomer, riskAvailable }: { invoices: Invoice[]; customers: Map<string, CustomerSummary>; riskByCustomer: Map<string, Risk>; riskAvailable: boolean }) {
  const pageSize = 30;
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<SortKey>("newest");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const visibleInvoices = useMemo(() => {
    const filtered = invoices.filter((invoice) => statusFilter === "all"
      || (statusFilter === "pending" && (invoice.status === "OPEN" || invoice.status === "PARTIALLY_PAID"))
      || (statusFilter === "overdue" && invoice.status === "OVERDUE")
      || (statusFilter === "disputed" && invoice.status === "DISPUTED"));
    return [...filtered].sort((left, right) => {
      let comparison = 0;
      if (sort === "newest" || sort === "oldest") comparison = left.issue_date.localeCompare(right.issue_date) * (sort === "newest" ? -1 : 1);
      if (sort === "invoice") comparison = left.invoice_number.localeCompare(right.invoice_number);
      if (sort === "customer") comparison = (customers.get(left.customer_id)?.name ?? "").localeCompare(customers.get(right.customer_id)?.name ?? "");
      if (sort === "due") comparison = left.due_date.localeCompare(right.due_date);
      if (sort === "exposure") comparison = Number(right.outstanding_amount) - Number(left.outstanding_amount);
      if (sort === "status") comparison = left.status.localeCompare(right.status);
      if (sort === "risk") {
        const leftRisk = riskByCustomer.get(left.customer_id);
        const rightRisk = riskByCustomer.get(right.customer_id);
        comparison = (riskRank[rightRisk?.level ?? "LOW"] - riskRank[leftRisk?.level ?? "LOW"]) || ((rightRisk?.score ?? 0) - (leftRisk?.score ?? 0));
      }
      return comparison || left.invoice_number.localeCompare(right.invoice_number);
    });
  }, [customers, invoices, riskByCustomer, sort, statusFilter]);
  const pages = Math.max(1, Math.ceil(visibleInvoices.length / pageSize));
  const rows = useMemo(() => visibleInvoices.slice(page * pageSize, (page + 1) * pageSize), [page, visibleInvoices]);
  const first = visibleInvoices.length ? page * pageSize + 1 : 0;
  const last = Math.min((page + 1) * pageSize, visibleInvoices.length);
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
  useEffect(() => setPage(0), [sort, statusFilter]);
  const previewInvoice = preview ? invoices.find((invoice) => invoice.id === preview.invoiceId) : null;

  return (
    <Panel className="mt-7">
      <SectionHeader
        eyebrow="Receivables register"
        title="Invoice operations register"
        detail="Sort and narrow the complete live invoice portfolio. Select any record for its factual profile."
        prominent
        action={
          <div className="flex items-center gap-3 text-xs text-slate-400">
            <span>{first}-{last} of {visibleInvoices.length}</span>
            <button aria-label="Previous invoice page" disabled={page === 0} onClick={() => setPage((value) => value - 1)} className="rounded-lg border border-white/[.08] px-2 py-1 text-sm hover:text-white disabled:opacity-30">Prev</button>
            <button aria-label="Next invoice page" disabled={page >= pages - 1} onClick={() => setPage((value) => value + 1)} className="rounded-lg border border-white/[.08] px-2 py-1 text-sm hover:text-white disabled:opacity-30">Next</button>
          </div>
        }
      />
      <div className="grid gap-3 border-b border-white/[.06] bg-white/[.015] p-4 lg:grid-cols-[auto_1fr] lg:items-center lg:px-5">
        <div className="flex flex-wrap items-center gap-2" aria-label="Invoice ordering">
          <span className="mr-1 text-[11px] font-bold uppercase tracking-[.12em] text-slate-400">Sort</span>
          <Control active={sort === "newest"} onClick={() => setSort("newest")}>Newest</Control>
          <Control active={sort === "oldest"} onClick={() => setSort("oldest")}>Oldest</Control>
          <Control active={sort === "risk"} disabled={!riskAvailable} title={riskAvailable ? "Sort by live customer intelligence" : "Live intelligence is unavailable"} onClick={() => setSort("risk")}>Risk</Control>
        </div>
        <div className="flex flex-wrap items-center gap-2 lg:justify-end" aria-label="Invoice status filter">
          <span className="mr-1 text-[11px] font-bold uppercase tracking-[.12em] text-slate-400">Status</span>
          {(["all", "pending", "overdue", "disputed"] as const).map((value) => <Control key={value} active={statusFilter === value} onClick={() => setStatusFilter(value)}>{value === "all" ? "All" : value === "disputed" ? "In dispute" : value[0].toUpperCase() + value.slice(1)}</Control>)}
        </div>
      </div>
      <div className="divide-y divide-white/[.055] md:hidden">
        {rows.map((invoice) => (
          <button type="button" key={invoice.id} onClick={(event) => openPreview(invoice, event.clientX, event.clientY)} className="interactive-row flex w-full items-start justify-between gap-4 p-4 text-left active:bg-sky-400/[.07]">
            <div className="min-w-0"><div className="flex items-center gap-2"><p className="truncate text-sm font-semibold text-white">{invoice.invoice_number}</p>{invoice.source === "CSV_IMPORT" && <StatusPill tone="sky">Imported</StatusPill>}</div><p className="mt-1 truncate text-[13px] text-slate-300">{customers.get(invoice.customer_id)?.name ?? "Portfolio account"}</p><p className="mt-2 text-xs text-slate-400">Due {invoice.due_date}</p></div>
            <div className="flex shrink-0 flex-col items-end gap-2"><p className="text-sm font-semibold tabular-nums text-white">{money(invoice.outstanding_amount)}</p><div className="flex flex-wrap justify-end gap-1.5"><StatusPill tone={statusTone(invoice.status)}>{invoice.status}</StatusPill>{riskAvailable && <StatusPill tone={riskTone(riskByCustomer.get(invoice.customer_id)?.level)}>{riskByCustomer.get(invoice.customer_id)?.level ?? "LOW"} risk</StatusPill>}</div></div>
          </button>
        ))}
        {!rows.length && <p className="px-5 py-10 text-center text-sm text-slate-500">No invoices match the selected status.</p>}
      </div>
      <div className="hidden overflow-x-auto md:block">
        <div className="min-w-[960px]">
          <div className="grid grid-cols-[1.15fr_1fr_.7fr_.75fr_.72fr_.72fr] gap-4 border-b border-white/[.08] bg-black/10 px-5 py-3 text-[11px] font-bold uppercase tracking-[.11em] text-slate-400">
            <SortHeader label="Invoice / account" active={sort === "invoice"} direction="A–Z" onClick={() => setSort("invoice")} />
            <SortHeader label="Customer" active={sort === "customer"} direction="A–Z" onClick={() => setSort("customer")} />
            <SortHeader label="Due date" active={sort === "due"} direction="↑" onClick={() => setSort("due")} />
            <SortHeader label="Exposure" active={sort === "exposure"} direction="↓" onClick={() => setSort("exposure")} />
            <SortHeader label="Status" active={sort === "status"} direction="A–Z" onClick={() => setSort("status")} />
            <SortHeader label="Risk" active={sort === "risk"} direction="↓" disabled={!riskAvailable} onClick={() => setSort("risk")} />
          </div>
          {rows.map((invoice) => (
            <button type="button" key={invoice.id} onClick={(event) => openPreview(invoice, event.clientX, event.clientY)} className="interactive-row grid w-full grid-cols-[1.15fr_1fr_.7fr_.75fr_.72fr_.72fr] gap-4 border-b border-white/[.045] px-5 py-4 text-left text-sm last:border-b-0 focus:bg-sky-400/[.06] focus:outline-none">
              <div>
                <div className="flex items-center gap-2"><p className="font-medium text-slate-200">{invoice.invoice_number}</p>{invoice.source === "CSV_IMPORT" && <StatusPill tone="sky">Imported</StatusPill>}</div>
                <p className="mt-0.5 text-[11px] text-slate-500">Issued {invoice.issue_date}</p>
              </div>
              <p className="truncate text-slate-300">{customers.get(invoice.customer_id)?.name ?? "Portfolio account"}</p>
              <p className="text-slate-300">{invoice.due_date}</p>
              <p className="font-semibold tabular-nums text-white">{money(invoice.outstanding_amount)}</p>
              <StatusPill tone={statusTone(invoice.status)}>{invoice.status}</StatusPill>
              {riskAvailable ? <StatusPill tone={riskTone(riskByCustomer.get(invoice.customer_id)?.level)}>{riskByCustomer.get(invoice.customer_id)?.level ?? "LOW"}</StatusPill> : <span className="text-xs text-slate-600">Unavailable</span>}
            </button>
          ))}
          {!rows.length && <p className={cx("px-5 py-10 text-center text-sm text-slate-500")}>No invoices match the selected status.</p>}
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
            <div><p className="text-[10px] font-bold uppercase tracking-[.16em] text-sky-300">Invoice profile</p><div className="mt-1 flex items-center gap-2"><h3 className="text-base font-semibold text-white">{previewInvoice.invoice_number}</h3>{previewInvoice.source === "CSV_IMPORT" && <StatusPill tone="sky">CSV import</StatusPill>}</div></div>
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
            {previewInvoice.latest_payment_amount && <div className="col-span-2 rounded-xl border border-emerald-300/12 bg-emerald-300/[.035] p-3"><dt className="text-[10px] uppercase tracking-[.1em] text-emerald-300">Latest persisted payment</dt><dd className="mt-1 font-semibold text-white">{money(previewInvoice.latest_payment_amount)} · {previewInvoice.latest_payment_date}</dd><dd className="mt-1 break-all text-[10px] text-slate-500">Reference {previewInvoice.latest_payment_reference ?? "not recorded"}</dd></div>}
          </dl>
          <p className="mt-4 text-[10px] leading-4 text-slate-500">Move onto this card to keep it open. Move away and it will fade automatically.</p>
        </aside>
      )}
    </Panel>
  );
}

function Control({ active, disabled = false, title, onClick, children }: { active: boolean; disabled?: boolean; title?: string; onClick: () => void; children: React.ReactNode }) {
  return <button type="button" disabled={disabled} title={title} aria-pressed={active} onClick={onClick} className={cx("rounded-lg border px-3 py-1.5 text-[11px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-35", active ? "border-sky-300/30 bg-sky-300/[.1] text-sky-100" : "border-white/[.08] bg-white/[.025] text-slate-400 hover:border-white/15 hover:text-white")}>{children}</button>;
}

function SortHeader({ label, active, direction, disabled = false, onClick }: { label: string; active: boolean; direction: string; disabled?: boolean; onClick: () => void }) {
  return <button type="button" disabled={disabled} onClick={onClick} className={cx("flex items-center gap-1.5 text-left transition hover:text-white disabled:cursor-not-allowed disabled:opacity-35", active && "text-sky-200")}><span>{label}</span><span aria-hidden="true" className={cx("text-[9px]", active ? "opacity-100" : "opacity-35")}>{direction}</span><span className="sr-only">{active ? `Currently sorted ${direction}` : `Sort by ${label}`}</span></button>;
}
