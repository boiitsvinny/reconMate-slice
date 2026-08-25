"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { CommandResultView } from "./command-result";
import { PROCESSING_STAGES, useCommandSession } from "./command-session";
import { buttonStyles, cx, Panel, SectionEyebrow, SectionHeader, StatusPill } from "@/components/dashboard/ui";

const examples = [
  "Who should I focus on today?",
  "Show me customers with broken promises",
  "Show top 5 high-risk customers",
  "Prepare recovery actions for critical cases",
  "Draft payment reminders for overdue customers",
  "Prepare follow ups for customers with broken promises",
  "Analyze portfolio health",
];

export function CommandCenter({ onOpenTarget }: { onOpenTarget?: (targetType: string, targetId: string) => boolean }) {
  const { activeCommand, result, processing, processingStage, error, runCommand, clearError } = useCommandSession();
  const [command, setCommand] = useState(activeCommand);
  const responseRef = useRef<HTMLDivElement>(null);

  useEffect(() => { if (activeCommand) setCommand(activeCommand); }, [activeCommand]);
  useEffect(() => {
    if (!result && !error) return;
    const frame = window.requestAnimationFrame(() => responseRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    return () => window.cancelAnimationFrame(frame);
  }, [error, result]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void runCommand({ command });
  };
  const runExample = (example: string) => {
    setCommand(example);
    void runCommand({ command: example });
  };

  return (
    <section className="mt-7" aria-label="ReconMate operational command center">
      <Panel className="overflow-hidden border-sky-300/15">
        <div className="relative p-5 sm:p-7">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_15%_0%,rgba(56,189,248,.1),transparent_42%)]" />
          <div className="relative">
            <SectionEyebrow>Intelligence command center</SectionEyebrow>
            <h2 className="mt-3 text-xl font-semibold tracking-[-.03em] text-white sm:text-2xl">What do you want ReconMate to work on?</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Ask about operational priorities, overdue exposure, broken promises, recovery work, or payment reminders.</p>
            <form onSubmit={submit} className="mt-5 flex flex-col gap-3 sm:flex-row">
              <label htmlFor="reconmate-command" className="sr-only">Operational command</label>
              <input
                id="reconmate-command"
                value={command}
                onChange={(event) => setCommand(event.target.value)}
                disabled={processing}
                placeholder="Enter an operational command..."
                autoComplete="off"
                className="min-h-12 min-w-0 flex-1 rounded-xl border border-white/[.12] bg-[#050d19]/75 px-4 text-sm text-white outline-none transition placeholder:text-slate-600 focus:border-sky-300/45 focus:ring-2 focus:ring-sky-300/10 disabled:opacity-60"
              />
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
      {error && (
        <div className="mt-5 flex flex-col justify-between gap-3 rounded-2xl border border-rose-300/20 bg-rose-300/[.06] p-4 sm:flex-row sm:items-center" role="alert">
          <div><p className="text-sm font-semibold text-rose-100">Command request failed</p><p className="mt-1 text-xs leading-5 text-rose-100/70">{error}</p></div>
          <button type="button" onClick={clearError} className={buttonStyles.secondary}>Dismiss</button>
        </div>
      )}

      {!processing && result && <CommandResultView command={activeCommand} result={result} onOpenTarget={onOpenTarget} />}
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

function activityStatus(status: "COMPLETED" | "PREPARED" | "AWAITING_CONFIRMATION" | "EXECUTED" | "FAILED") {
  return status === "AWAITING_CONFIRMATION" ? "Decision required" : status === "EXECUTED" ? "Action recorded" : status === "COMPLETED" ? "Analysis complete" : status.replaceAll("_", " ");
}

function activityDescription(status: "COMPLETED" | "PREPARED" | "AWAITING_CONFIRMATION" | "EXECUTED" | "FAILED") {
  return status === "AWAITING_CONFIRMATION" ? "Plan prepared; waiting for operator confirmation." : status === "EXECUTED" ? "Internal workflow action recorded." : status === "PREPARED" ? "Preparation completed; nothing was sent." : status === "COMPLETED" ? "Read-only analysis completed." : "Command did not create workflow work.";
}
