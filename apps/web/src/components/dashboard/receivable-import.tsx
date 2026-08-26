"use client";

import { useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { buttonStyles, cx, StatusPill } from "./ui";

type PreviewRow = {
  row_number: number;
  customer_reference: string;
  customer_name: string;
  invoice_number: string;
  original_amount: string | null;
  outstanding_amount: string | null;
  issue_date: string | null;
  due_date: string | null;
  currency: string;
  status: string | null;
  validation_status: "VALID" | "INVALID" | "DUPLICATE";
  errors: string[];
};

type ImportPreview = {
  rows_detected: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  total_original_amount: string;
  total_outstanding_amount: string;
  required_columns: string[];
  optional_columns: string[];
  file_errors: string[];
  rows: PreviewRow[];
};

type ImportResult = {
  customers_created: number;
  invoices_created: number;
  recovery_cases_created: number;
  duplicates_skipped: number;
  total_outstanding_imported: string;
  evaluation_date: string;
  message: string;
};

const sample = [
  "customer_reference,customer_name,invoice_number,original_amount,outstanding_amount,issue_date,due_date,currency,status",
  "EXT-001,Example Trading Co,EXT-INV-001,125000.00,125000.00,2026-07-01,2026-08-01,INR,OVERDUE",
].join("\n");

const money = (value: string | null) => value === null ? "—" : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value));

export function ReceivableImport({ onImported }: { onImported: () => Promise<unknown> }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [fileName, setFileName] = useState("");
  const [csvText, setCsvText] = useState("");
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const chooseFile = () => inputRef.current?.click();
  const close = () => { if (!busy) setOpen(false); };
  const load = async (file?: File) => {
    if (!file) return;
    setBusy(true); setError(null); setPreview(null); setResult(null); setFileName(file.name);
    try {
      const text = await file.text();
      setCsvText(text);
      const response = await apiFetch("/imports/receivables/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ csv_text: text }) }, 60_000);
      if (!response.ok) throw new Error(await responseError(response, "The CSV could not be validated."));
      setPreview(await response.json() as ImportPreview);
      setOpen(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The CSV could not be validated.");
      setOpen(true);
    } finally { setBusy(false); if (inputRef.current) inputRef.current.value = ""; }
  };
  const confirm = async () => {
    if (!preview || preview.invalid_rows || preview.file_errors.length || !preview.valid_rows) return;
    setBusy(true); setError(null);
    try {
      const response = await apiFetch("/imports/receivables/confirm", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ csv_text: csvText }) }, 90_000);
      if (!response.ok) throw new Error(await responseError(response, "The import was not persisted."));
      setResult(await response.json() as ImportResult);
      await onImported();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The import was not persisted.");
    } finally { setBusy(false); }
  };

  return <>
    <input ref={inputRef} type="file" accept=".csv,text/csv" className="sr-only" onChange={(event) => void load(event.target.files?.[0])} />
    <button type="button" onClick={chooseFile} className={buttonStyles.primary}>Import receivables</button>
    {open && <div className="fixed inset-0 z-50 grid place-items-center bg-[#030712]/75 p-3 backdrop-blur-sm" onClick={close} role="presentation">
      <section role="dialog" aria-modal="true" aria-label="Import receivables" onClick={(event) => event.stopPropagation()} className="max-h-[92vh] w-full max-w-5xl overflow-y-auto rounded-2xl border border-white/[.12] bg-[#0b1526] shadow-2xl shadow-black/60">
        <header className="flex flex-col justify-between gap-4 border-b border-white/[.07] p-5 sm:flex-row sm:items-start">
          <div><p className="text-[11px] font-bold uppercase tracking-[.16em] text-sky-300">External data intake</p><h2 className="mt-2 text-2xl font-semibold text-white">Import receivables</h2><p className="mt-2 max-w-3xl text-[13px] leading-5 text-slate-400">Upload → validate → preview → confirm. No portfolio record changes until confirmation succeeds.</p></div>
          <button type="button" onClick={close} disabled={busy} className={buttonStyles.secondary}>Close</button>
        </header>
        <div className="space-y-5 p-5">
          <div className="flex flex-col justify-between gap-3 rounded-xl border border-sky-300/12 bg-sky-300/[.03] p-4 sm:flex-row sm:items-center"><div><p className="text-sm font-semibold text-white">{fileName || "No CSV selected"}</p><p className="mt-1 text-xs text-slate-400">Required: customer reference, customer name, invoice number, amounts, invoice date, and due date.</p></div><div className="flex flex-wrap gap-2"><a className={buttonStyles.secondary} href={`data:text/csv;charset=utf-8,${encodeURIComponent(sample)}`} download="reconmate-receivables-sample.csv">Download sample</a><button type="button" onClick={chooseFile} disabled={busy} className={buttonStyles.secondary}>Choose another CSV</button></div></div>
          <p className="rounded-xl border border-emerald-300/12 bg-emerald-300/[.035] p-3 text-xs leading-5 text-emerald-100/80"><strong>Data origin:</strong> Demo Sandbox remains synthetic and replayable. CSV imports are user-supplied receivables that enter the same persisted intelligence and recommendation path.</p>
          {error && <p role="alert" className="rounded-xl border border-rose-300/20 bg-rose-300/[.06] p-3 text-sm text-rose-100">{error}</p>}
          {busy && !preview && <div className="h-32 animate-pulse rounded-xl bg-white/[.04]" role="status"><span className="sr-only">Validating CSV</span></div>}
          {preview && <>
            <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-white/[.07] bg-white/[.07] md:grid-cols-6"><ImportMetric label="Rows detected" value={String(preview.rows_detected)} /><ImportMetric label="Valid" value={String(preview.valid_rows)} tone="emerald" /><ImportMetric label="Invalid" value={String(preview.invalid_rows)} tone={preview.invalid_rows ? "rose" : "slate"} /><ImportMetric label="Duplicates" value={String(preview.duplicate_rows)} tone={preview.duplicate_rows ? "amber" : "slate"} /><ImportMetric label="Original total" value={money(preview.total_original_amount)} /><ImportMetric label="Outstanding import" value={money(preview.total_outstanding_amount)} /></div>
            {preview.file_errors.length > 0 && <ul className="rounded-xl border border-rose-300/20 bg-rose-300/[.06] p-4 text-sm text-rose-100">{preview.file_errors.map((item) => <li key={item}>• {item}</li>)}</ul>}
            <div className="overflow-x-auto rounded-xl border border-white/[.07]"><table className="min-w-[900px] w-full text-left text-xs"><thead className="bg-black/15 text-[10px] uppercase tracking-[.1em] text-slate-400"><tr><th className="p-3">Row</th><th>Customer</th><th>Invoice</th><th>Original</th><th>Outstanding</th><th>Dates</th><th>Status</th><th>Validation</th></tr></thead><tbody className="divide-y divide-white/[.055]">{preview.rows.slice(0, 50).map((row) => <tr key={row.row_number} className="align-top"><td className="p-3 text-slate-500">{row.row_number}</td><td className="py-3 pr-3"><p className="font-semibold text-slate-200">{row.customer_name || "Missing"}</p><p className="mt-1 text-slate-500">{row.customer_reference || "No reference"}</p></td><td className="py-3 pr-3 text-slate-300">{row.invoice_number || "Missing"}</td><td className="py-3 pr-3 tabular-nums text-slate-300">{money(row.original_amount)}</td><td className="py-3 pr-3 tabular-nums text-slate-300">{money(row.outstanding_amount)}</td><td className="py-3 pr-3 text-slate-400">{row.issue_date ?? "—"}<br />{row.due_date ?? "—"}</td><td className="py-3 pr-3 text-slate-300">{row.status ?? "Derived"}</td><td className="py-3 pr-3"><StatusPill tone={row.validation_status === "VALID" ? "emerald" : row.validation_status === "DUPLICATE" ? "amber" : "rose"}>{row.validation_status}</StatusPill>{row.errors.map((item) => <p key={item} className="mt-1 max-w-xs leading-4 text-rose-200/80">{item}</p>)}</td></tr>)}</tbody></table></div>
            {preview.rows.length > 50 && <p className="text-xs text-slate-500">Showing the first 50 of {preview.rows.length} rows.</p>}
            <div className="flex flex-col justify-between gap-3 border-t border-white/[.07] pt-4 sm:flex-row sm:items-center"><p className="max-w-2xl text-xs leading-5 text-slate-400">Duplicates are skipped. Invalid rows block the entire import so financial records are never partially persisted.</p><button type="button" onClick={() => void confirm()} disabled={busy || Boolean(result) || preview.invalid_rows > 0 || preview.file_errors.length > 0 || preview.valid_rows === 0} className={cx(buttonStyles.primary, "disabled:cursor-not-allowed disabled:opacity-40")}>{result ? "Import completed" : busy ? "Persisting and refreshing…" : `Confirm import of ${preview.valid_rows} row${preview.valid_rows === 1 ? "" : "s"}`}</button></div>
          </>}
          {result && <div className="rounded-xl border border-emerald-300/20 bg-emerald-300/[.05] p-5"><div className="flex items-center justify-between gap-3"><h3 className="text-lg font-semibold text-white">Import completed</h3><StatusPill tone="emerald">Persisted</StatusPill></div><p className="mt-2 text-sm leading-6 text-emerald-100/80">{result.invoices_created} invoices across {result.customers_created} new customers were persisted; {result.duplicates_skipped} duplicates were skipped. {result.recovery_cases_created} recovery cases entered the existing evaluation path for operating date {result.evaluation_date}.</p><p className="mt-2 text-xs text-slate-400">Imported outstanding: {money(result.total_outstanding_imported)}. Close this window to inspect the records in the ledger.</p></div>}
        </div>
      </section>
    </div>}
  </>;
}

async function responseError(response: Response, fallback: string) {
  const payload = await response.json().catch(() => null) as { detail?: string | { message?: string } } | null;
  return typeof payload?.detail === "string" ? payload.detail : payload?.detail?.message ?? fallback;
}

function ImportMetric({ label, value, tone = "slate" }: { label: string; value: string; tone?: "slate" | "emerald" | "amber" | "rose" }) {
  const colors = { slate: "text-white", emerald: "text-emerald-200", amber: "text-amber-100", rose: "text-rose-200" };
  return <div className="bg-[#08111f] p-4"><p className="text-[10px] font-bold uppercase tracking-[.1em] text-slate-500">{label}</p><p className={`mt-2 text-lg font-semibold tabular-nums ${colors[tone]}`}>{value}</p></div>;
}
