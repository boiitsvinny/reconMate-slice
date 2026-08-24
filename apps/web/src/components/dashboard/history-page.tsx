"use client";

import { useMemo } from "react";
import { AppHeader } from "@/components/layout/app-header";
import { InvoiceRegister } from "./invoice-register";
import { useCustomers, useInvoices } from "./queries";

export function HistoryPage() {
  const customers = useCustomers();
  const invoices = useInvoices();
  const ready = Boolean(customers.data && invoices.data);
  const error = customers.error ?? invoices.error;
  const errorMessage = error instanceof Error ? error.message : error ? "Unable to load invoice history." : null;
  const customerMap = useMemo(() => new Map(customers.data?.map((customer) => [customer.id, customer]) ?? []), [customers.data]);

  return (
    <main className="min-h-screen overflow-x-hidden">
      <AppHeader connected={ready} updating={ready && (customers.isFetching || invoices.isFetching)} />
      <div className="mx-auto max-w-[1580px] px-4 py-6 pb-24 sm:px-6 sm:py-8 sm:pb-10 lg:px-10 lg:py-10">
        <header className="max-w-3xl">
          <p className="text-[11px] font-bold uppercase tracking-[.22em] text-sky-200">Receivables history</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-.04em] text-white sm:text-4xl">Invoice History</h1>
          <p className="mt-3 text-sm leading-6 text-slate-300/80">Review every live invoice record. Select a row to inspect its invoice and customer profile beside your pointer.</p>
        </header>
        {!ready && errorMessage && <PageError message={errorMessage} onRetry={async () => { await Promise.all([customers.refetch(), invoices.refetch()]); }} />}
        {!ready && !errorMessage && <PageSkeleton />}
        {ready && errorMessage && <p className="mt-5 rounded-xl border border-amber-300/15 bg-amber-300/[.06] px-4 py-3 text-xs text-amber-100">Live refresh is delayed. Showing cached invoice data.</p>}
        {invoices.data && <InvoiceRegister invoices={invoices.data} customers={customerMap} />}
      </div>
    </main>
  );
}

function PageError({ message, onRetry }: { message: string; onRetry: () => Promise<void> }) {
  return <div className="mt-7 flex items-center justify-between gap-4 rounded-2xl border border-rose-300/20 bg-rose-300/[.07] p-5"><p className="text-sm text-rose-100">{message}</p><button onClick={() => void onRetry()} className="rounded-lg border border-rose-200/25 px-3 py-2 text-xs font-bold text-rose-50">Try again</button></div>;
}

function PageSkeleton() {
  return <div role="status" aria-label="Loading invoice history" className="mt-7 h-[560px] animate-pulse rounded-2xl border border-white/[.07] bg-white/[.035]"><span className="sr-only">Loading invoices</span></div>;
}
