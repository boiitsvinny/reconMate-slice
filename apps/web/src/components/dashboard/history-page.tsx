"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AppHeader } from "@/components/layout/app-header";
import { Customer, fetchJson, Invoice } from "./data";
import { InvoiceRegister } from "./invoice-register";

export function HistoryPage() {
  const [data, setData] = useState<{ customers: Customer[]; invoices: Invoice[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      const [customers, invoices] = await Promise.all([fetchJson<Customer[]>("/customers"), fetchJson<Invoice[]>("/invoices")]);
      setData({ customers, invoices });
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load invoice history.");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  const customerMap = useMemo(() => new Map(data?.customers.map((customer) => [customer.id, customer]) ?? []), [data?.customers]);

  return (
    <main className="min-h-screen overflow-x-hidden">
      <AppHeader connected={Boolean(data)} />
      <div className="mx-auto max-w-[1580px] px-4 py-8 sm:px-6 lg:px-10 lg:py-10">
        <header className="max-w-3xl">
          <p className="text-[11px] font-bold uppercase tracking-[.22em] text-sky-200">Receivables history</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-.04em] text-white sm:text-4xl">Invoice History</h1>
          <p className="mt-3 text-sm leading-6 text-slate-300/80">Review every live invoice record. Select a row to inspect its invoice and customer profile beside your pointer.</p>
        </header>
        {error && <PageError message={error} onRetry={load} />}
        {!data && !error && <PageSkeleton />}
        {data && <InvoiceRegister invoices={data.invoices} customers={customerMap} />}
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
