"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import type { Customer, PriorityCase } from "@/components/dashboard/data";
import { CommandResultView } from "./command-result";
import { PROCESSING_STAGES, useCommandSession } from "./command-session";
import { resolveCustomerLookup, type CustomerLookup } from "./customer-lookup";
import { buttonStyles, cx, Panel, SectionEyebrow, SectionHeader, StatusPill } from "@/components/dashboard/ui";

const examples = [
  "Analyze Mintleaf Office Mart",
  "Who should I focus on today?",
  "Show customers with broken promises",
  "Show customers blocked by disputes",
  "What changed this cycle?",
];

type CommandCenterProps = {
  customers?: Customer[];
  queue?: PriorityCase[];
  onOpenTarget?: (targetType: string, targetId: string) => boolean;
  onOpenWorkspace?: (customerId: string) => boolean;
};

export function CommandCenter({ customers = [], queue = [], onOpenTarget, onOpenWorkspace }: CommandCenterProps) {
  const { activeCommand, result, processing, processingStage, error, runCommand, clearError } = useCommandSession();
  const [command, setCommand] = useState(activeCommand);
  const [lookup, setLookup] = useState<CustomerLookup>({ kind: "none" });
  const [matchedCustomerId, setMatchedCustomerId] = useState<string | null>(null);
  const responseRef = useRef<HTMLDivElement>(null);

  useEffect(() => { if (activeCommand) setCommand(activeCommand); }, [activeCommand]);
  useEffect(() => {
    if (!result && !error) return;
    const frame = window.requestAnimationFrame(() => responseRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    return () => window.cancelAnimationFrame(frame);
  }, [error, result]);

  const execute = (value: string) => {
    clearError();
    const resolution = resolveCustomerLookup(value, customers, Boolean(matchedCustomerId));
    if (resolution.kind === "ambiguous" || resolution.kind === "not-found") {
      setLookup(resolution);
      return;
    }
    const customerId = resolution.kind === "match" ? resolution.customer.id : resolution.kind === "context" ? matchedCustomerId : null;
    setLookup({ kind: "none" });
    if (resolution.kind === "match") setMatchedCustomerId(resolution.customer.id);
    void runCommand({ command: value, context_customer_id: customerId });
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    execute(command);
  };
  const runExample = (example: string) => {
    setCommand(example);
    execute(example);
  };
  const chooseCustomer = (customer: Customer) => {
    if (lookup.kind !== "ambiguous") return;
    const preservedQuery = lookup.query;
    setMatchedCustomerId(customer.id);
    setLookup({ kind: "none" });
    setCommand(preservedQuery);
    void runCommand({ command: preservedQuery, context_customer_id: customer.id });
  };
  const matchedCustomer = customers.find((customer) => customer.id === matchedCustomerId);
  const matchedCases = matchedCustomerId ? queue.filter((item) => item.customerId === matchedCustomerId) : [];

  return (
    <section className="mt-7" aria-label="ReconMate operational command center">
      <Panel className="overflow-hidden border-sky-300/15">
        <div className="relative p-5 sm:p-7">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_15%_0%,rgba(56,189,248,.1),transparent_42%)]" />
          <div className="relative">
            <SectionEyebrow>Intelligence command center</SectionEyebrow>
            <h2 className="mt-3 text-xl font-semibold tracking-[-.03em] text-white sm:text-2xl">What do you want ReconMate to work on?</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Ask about operational priorities, overdue exposure, broken promises, recovery work, or payment reminders.</p>
            <p className="mt-2 text-[11px] leading-5 text-slate-500">Customer lookup and recovery decisions are deterministic. Model-backed AI is limited to interpreting unstructured customer communications; operators control material actions.</p>
            <form onSubmit={submit} className="mt-5 flex flex-col gap-3 sm:flex-row">
              <div className="intelligence-input-shell min-w-0 flex-1">
                <label htmlFor="reconmate-command" className="sr-only">Operational command</label>
                <input
                  id="reconmate-command"
                  value={command}
                  onChange={(event) => setCommand(event.target.value)}
                  disabled={processing}
                  placeholder="Enter an operational command..."
                  autoComplete="off"
                  className="intelligence-command-input min-h-12 w-full min-w-0 rounded-[11px] px-4 text-sm text-white outline-none placeholder:text-slate-600 disabled:opacity-60"
                />
              </div>
              <button disabled={processing || !command.trim()} className={`${buttonStyles.primary} min-h-12 px-6 sm:w-auto`}>{processing ? "Analyzing..." : "Analyze"}</button>
            </form>
            <div className="mt-4 flex flex-wrap gap-2" aria-label="Supported command examples">
              {examples.map((example) => <button type="button" disabled={processing} key={example} onClick={() => runExample(example)} className="rounded-full border border-white/[.08] bg-white/[.025] px-3 py-1.5 text-left text-[11px] text-slate-400 transition hover:border-sky-300/25 hover:text-sky-100 disabled:opacity-50">Try: {example}</button>)}
            </div>
          </div>
        </div>
        {processing && (
          <div className="border-t border-sky-300/10 bg-sky-300/[.025] p-5" role="status" aria-live="polite">
            <p className="text-xs font-semibold text-sky-100">{PROCESSING_STAGES[processingStage]}</p>
            <div className="mt-3 grid grid-cols-5 gap-1.5" aria-hidden="true">
              {PROCESSING_STAGES.map((stage, index) => <span key={stage} className={cx("h-1 rounded-full transition", index <= processingStage ? "bg-sky-300" : "bg-white/[.07]")} />)}
            </div>
            <p className="mt-2 text-[10px] text-slate-500">ReconMate is evaluating current operational records and building a bounded result.</p>
          </div>
        )}
      </Panel>

      <div ref={responseRef} className="scroll-mt-24">
      {lookup.kind === "ambiguous" && (
        <Panel className="mt-5 overflow-hidden border-amber-300/15">
          <SectionHeader eyebrow="Choose an account" title="More than one customer may match" detail={`ReconMate preserved “${lookup.query}” and did not guess.`} prominent />
          <div className="grid gap-2 p-4 sm:grid-cols-2">
            {lookup.customers.map((customer) => <button key={customer.id} type="button" onClick={() => chooseCustomer(customer)} className="rounded-xl border border-white/[.08] bg-white/[.025] p-4 text-left transition hover:border-sky-300/30 hover:bg-sky-300/[.05]"><span className="block text-sm font-semibold text-white">{customer.name}</span><span className="mt-1 block text-[11px] text-slate-500">{customer.account_reference}</span></button>)}
          </div>
        </Panel>
      )}
      {lookup.kind === "not-found" && (
        <Panel className="mt-5 overflow-hidden border-amber-300/15">
          <SectionHeader eyebrow="No customer match" title="No customer was found for this query" detail={`Your request was preserved: “${lookup.query}”`} prominent />
          <div className="p-5 text-xs leading-5 text-slate-400">Try a full or partial account name, or ask about overdue exposure, broken promises, disputes, current priorities, or latest-cycle changes. “This customer” requires a customer to be selected first.</div>
        </Panel>
      )}
      {error && (
        <div className="mt-5 flex flex-col justify-between gap-3 rounded-2xl border border-rose-300/20 bg-rose-300/[.06] p-4 sm:flex-row sm:items-center" role="alert">
          <div><p className="text-sm font-semibold text-rose-100">Command request failed</p><p className="mt-1 text-xs leading-5 text-rose-100/70">{error}</p></div>
          <button type="button" onClick={clearError} className={buttonStyles.secondary}>Dismiss</button>
        </div>
      )}

      {!processing && lookup.kind === "none" && result && <CommandResultView command={activeCommand} result={result} onOpenTarget={onOpenTarget} onOpenWorkspace={onOpenWorkspace} customer={matchedCustomer} customerCases={matchedCases} onTryCommand={runExample} />}
      </div>
    </section>
  );
}

export function CommandActivityPanel() {
  const { history, openActivity } = useCommandSession();
  return (
    <Panel className="overflow-hidden">
      <SectionHeader eyebrow="Today's command activity" title="Current browser session" detail={`${history.length} command${history.length === 1 ? "" : "s"} retained in this browser session`} prominent />
      <div className="operational-scrollbar max-h-72 divide-y divide-white/[.055] overflow-y-auto overscroll-contain" role="region" aria-label="Current command activity" tabIndex={0}>
        {history.map((item) => (
          <article key={item.planId} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-slate-200">{item.command}</p>
              <p className="mt-1 text-[11px] leading-4 text-slate-500">{activityDescription(item.status)} {item.analyzedCount} records inspected / {item.proposalCount} proposals / {new Date(item.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</p>
              <p className="mt-1 line-clamp-1 text-[11px] text-slate-400">{item.summary}</p>
            </div>
            <div className="flex items-center gap-2 self-end sm:self-auto"><StatusPill tone={item.status === "FAILED" ? "rose" : item.status === "AWAITING_CONFIRMATION" ? "amber" : item.status === "EXECUTED" ? "emerald" : "sky"}>{activityStatus(item.status)}</StatusPill>{item.resultSnapshot && <button type="button" onClick={() => openActivity(item.planId)} className={buttonStyles.secondary}>Open result</button>}</div>
          </article>
        ))}
        {!history.length && <p className="p-8 text-center text-xs text-slate-500">No commands have been run in this browser session.</p>}
      </div>
    </Panel>
  );
}

export function CommandNotices() {
  const { result } = useCommandSession();
  if (!result || (!result.warnings.length && !result.limitations.length)) return null;
  const notices = [...result.warnings, ...result.limitations];
  return <details className="mt-7 rounded-2xl border border-white/[.08] bg-[#08111f]/80 p-4 sm:p-5"><summary className="cursor-pointer text-sm font-semibold text-slate-300">Notices and operating boundaries ({notices.length})</summary><ul className="mt-3 space-y-2 text-xs leading-5 text-slate-500">{notices.map((item) => <li key={item}>• {item}</li>)}</ul></details>;
}

function activityStatus(status: "COMPLETED" | "PREPARED" | "AWAITING_CONFIRMATION" | "EXECUTED" | "FAILED") {
  return status === "AWAITING_CONFIRMATION" ? "Decision required" : status === "EXECUTED" ? "Action recorded" : status === "COMPLETED" ? "Analysis complete" : status.replaceAll("_", " ");
}

function activityDescription(status: "COMPLETED" | "PREPARED" | "AWAITING_CONFIRMATION" | "EXECUTED" | "FAILED") {
  return status === "AWAITING_CONFIRMATION" ? "Plan prepared; waiting for operator confirmation." : status === "EXECUTED" ? "Internal workflow action recorded." : status === "PREPARED" ? "Preparation completed; nothing was sent." : status === "COMPLETED" ? "Read-only analysis completed." : "Command did not create workflow work.";
}
