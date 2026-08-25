"use client";

import { useMemo } from "react";
import { AppHeader } from "@/components/layout/app-header";
import { InvoiceRegister } from "./invoice-register";
import { useCustomers, useInvoices, usePortfolioIntelligence } from "./queries";

export function HistoryPage() {
  const customers = useCustomers();
  const invoices = useInvoices();
  const intelligence = usePortfolioIntelligence();
  const ready = Boolean(customers.data && invoices.data);
  const error = customers.error ?? invoices.error;
  const errorMessage = error instanceof Error ? error.message : error ? "Unable to load invoice history." : null;
  const intelligenceError = intelligence.error instanceof Error ? intelligence.error.message : intelligence.isError ? "Risk intelligence is temporarily unavailable." : null;
  const customerMap = useMemo(() => new Map(customers.data?.map((customer) => [customer.id, customer]) ?? []), [customers.data]);
  const riskByCustomer = useMemo(() => new Map(intelligence.data?.customers.map((item) => [item.entity_id, { level: item.level, score: item.score }]) ?? []), [intelligence.data]);

  return (
    <main className="min-h-screen overflow-x-hidden">
      <AppHeader connected={ready && !errorMessage && !intelligenceError} updating={ready && !errorMessage && !intelligenceError && (customers.isFetching || invoices.isFetching || intelligence.isFetching)} />
      <div className="mx-auto max-w-[1580px] px-4 py-6 pb-24 sm:px-6 sm:py-8 sm:pb-10 lg:px-10 lg:py-10">
        <header className="max-w-3xl">
          <p className="text-[11px] font-bold uppercase tracking-[.22em] text-sky-200">Receivables history</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-.04em] text-white sm:text-4xl">Invoice History</h1>
          <p className="mt-3 text-sm leading-6 text-slate-300/80">Review every live invoice record. Select a row to inspect its invoice and customer profile beside your pointer.</p>
        </header>
        {!ready && errorMessage && <PageError message={errorMessage} onRetry={async () => { await Promise.all([customers.refetch(), invoices.refetch()]); }} />}
        {!ready && !errorMessage && <PageSkeleton />}
        {ready && (errorMessage || intelligenceError) && <div className="mt-5 flex flex-col justify-between gap-3 rounded-xl border border-amber-300/15 bg-amber-300/[.06] px-4 py-3 sm:flex-row sm:items-center"><p className="text-xs text-amber-100">{errorMessage ? "Live refresh is delayed. Showing the last successful invoice data." : "Invoice records are available, but current risk intelligence could not be loaded."}</p><button type="button" onClick={() => void Promise.all([customers.refetch(), invoices.refetch(), intelligence.refetch()])} className="text-xs font-semibold text-amber-50 underline decoration-amber-200/30 underline-offset-4">Retry refresh</button></div>}
        {invoices.data && <InvoiceRegister invoices={invoices.data} customers={customerMap} riskByCustomer={riskByCustomer} riskAvailable={Boolean(intelligence.data)} />}
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
