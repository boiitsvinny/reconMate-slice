"use client";

import { useEffect, useState } from "react";
import type { ReminderArtifact as ReminderArtifactData } from "@/lib/intelligence-api";
import { buttonStyles, StatusPill } from "@/components/dashboard/ui";

const money = (value: string) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value));

export function ReminderArtifact({ artifact }: { artifact: ReminderArtifactData }) {
  const [body, setBody] = useState(artifact.body ?? "");
  const [editing, setEditing] = useState(false);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => { setBody(artifact.body ?? ""); setEditing(false); setCopyState("idle"); }, [artifact]);

  const copy = async () => {
    try { await navigator.clipboard.writeText(body); setCopyState("copied"); }
    catch { setCopyState("failed"); }
  };

  const available = artifact.status === "PREPARED_FOR_REVIEW" && Boolean(artifact.body);
  return (
    <section className="mt-4 rounded-xl border border-sky-300/20 bg-[#071426]/75 p-4" aria-label="Prepared reminder artifact">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-[10px] font-bold uppercase tracking-[.14em] text-sky-300">Prepared reminder</p><h4 className="mt-1 text-base font-semibold text-white">{artifact.customer_name}</h4><p className="mt-1 text-[10px] text-slate-500">Prepared {new Date(artifact.prepared_at).toLocaleString()} / {artifact.intended_channel}</p></div><StatusPill tone={available ? "sky" : artifact.status === "BLOCKED" ? "rose" : "amber"}>{artifact.status.replaceAll("_", " ")}</StatusPill></div>
      <p className="mt-3 text-xs leading-5 text-slate-300">{artifact.reason}</p>
      <div className="mt-3 rounded-lg border border-white/[.07] bg-black/10 p-3"><p className="text-[9px] font-bold uppercase tracking-[.12em] text-slate-500">Based on current facts</p><ul className="mt-2 space-y-1 text-[11px] text-slate-300"><li>{artifact.invoices.length} overdue invoice{artifact.invoices.length === 1 ? "" : "s"} / {money(artifact.total_outstanding)} outstanding</li><li>Promise state: {artifact.promise_state.replaceAll("_", " ")} / dispute state: {artifact.dispute_state.replaceAll("_", " ")}</li><li>Purpose: {artifact.purpose} / tone: {artifact.tone}</li></ul></div>
      {artifact.invoices.length > 0 && <div className="mt-3 space-y-1.5">{artifact.invoices.map((invoice) => <div key={invoice.invoice_number} className="flex flex-wrap justify-between gap-2 rounded-lg border border-white/[.06] px-3 py-2 text-[11px]"><span className="font-semibold text-slate-200">{invoice.invoice_number}</span><span className="text-slate-400">{money(invoice.outstanding_amount)} / due {invoice.due_date} / {invoice.days_overdue} days overdue</span></div>)}</div>}
      {available && <><label className="mt-4 block text-[10px] font-bold uppercase tracking-[.12em] text-slate-500" htmlFor={`reminder-${artifact.account_reference}`}>Reminder draft</label><textarea id={`reminder-${artifact.account_reference}`} value={body} readOnly={!editing} onChange={(event) => setBody(event.target.value)} rows={7} className="mt-2 w-full rounded-xl border border-white/[.09] bg-black/20 p-3 text-xs leading-5 text-slate-200 outline-none focus:border-sky-300/35 read-only:text-slate-300"/><div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={() => setEditing((value) => !value)} className={buttonStyles.secondary}>{editing ? "Finish editing" : "Edit draft"}</button><button type="button" onClick={() => void copy()} className={buttonStyles.primary}>{copyState === "copied" ? "Copied" : copyState === "failed" ? "Copy failed" : "Copy draft"}</button><button type="button" onClick={() => { setBody(artifact.body ?? ""); setEditing(false); }} className={buttonStyles.secondary}>Restore grounded draft</button></div></>}
      <p className="mt-4 rounded-lg border border-emerald-300/15 bg-emerald-300/[.045] px-3 py-2 text-xs font-semibold text-emerald-100">Prepared only — no customer communication has been sent.</p>
      {available && <p className="mt-2 text-[10px] leading-4 text-slate-500">Editing or copying changes only this browser draft. It does not modify invoice, payment, promise, dispute, or case facts.</p>}
    </section>
  );
}
