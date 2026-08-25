"use client";

import { useEffect, useState } from "react";
import { buttonStyles, cx } from "./ui";
import type { IntelligenceTransition } from "./data";

type Props = {
  cycle: number;
  simulationDate: string;
  interval: number;
  busy: boolean;
  resetting: boolean;
  auto: boolean;
  feedback?: CycleFeedback;
  resetFeedback?: ResetFeedback;
  onAutoChange: (enabled: boolean) => void;
  onTick: () => void;
  onReset: () => void;
};

export type CycleFeedback = {
  status: "MATERIAL_CHANGE" | "NO_MATERIAL_CHANGE" | "REFRESH_FAILED";
  headline: string;
  event: string;
  summary: string;
  changes: string[];
  transition?: IntelligenceTransition;
};

export type ResetFeedback = {
  status: "SUCCESS" | "REFRESH_FAILED";
  message: string;
};

export function SimulationControl({ cycle, simulationDate, interval, busy, resetting, auto, feedback, resetFeedback, onAutoChange, onTick, onReset }: Props) {
  const [remaining, setRemaining] = useState(interval);

  useEffect(() => {
    setRemaining(interval);
  }, [cycle, interval, auto]);

  useEffect(() => {
    if (!auto || busy) return;
    const timer = window.setInterval(() => setRemaining((value) => value > 0 ? value - 1 : interval), 1000);
    return () => window.clearInterval(timer);
  }, [auto, busy, interval]);

  return (
    <section className="relative overflow-hidden rounded-2xl border border-sky-300/20 bg-[#08111f]/95 p-4 shadow-[0_18px_45px_rgba(0,0,0,.22)]">
      <div className="absolute inset-y-0 left-0 w-1 rounded-l-2xl bg-sky-400" />
      <div className="pl-2">
        <p className="text-[10px] font-bold uppercase tracking-[.16em] text-sky-300">Demo simulation</p>
        <h2 className="mt-2 text-xl font-semibold tracking-[-.025em] text-white sm:text-2xl">Advance the operating cycle</h2>
        <p className="mt-1 text-[11px] leading-4 text-slate-500">Run a cycle to persist operational changes, re-evaluate the portfolio, and refresh recommendations.</p>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-4 border-y border-white/[.07] py-3 pl-2">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[.18em] text-sky-300">
            <span className={cx("mr-2 inline-block h-1.5 w-1.5", auto ? "animate-pulse bg-emerald-400" : "bg-slate-500")} />
            Simulation {auto ? "live" : "paused"}
          </p>
          <p className="mt-1 text-xs text-slate-400">
            Cycle <span className="font-semibold text-white">{cycle}</span> / virtual operating date <span className="font-semibold text-slate-200">{simulationDate}</span>
          </p>
        </div>
        <div className="border-l border-white/[.08] pl-4 text-right">
          <p className="text-xl font-semibold tabular-nums text-white">{auto ? `${remaining}s` : "-"}</p>
          <p className="text-[10px] uppercase tracking-[.12em] text-slate-500">next cycle</p>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-1 pl-2 text-center text-[9px] font-semibold uppercase tracking-[.08em] text-slate-500" aria-label="Simulation cause and effect">
        <span className="rounded-md bg-white/[.03] px-2 py-1.5">Events occur</span>
        <span className="rounded-md bg-white/[.03] px-2 py-1.5">Facts evaluated</span>
        <span className="rounded-md bg-white/[.03] px-2 py-1.5">Focus refreshes</span>
      </div>
      <div className="mt-4 flex flex-wrap gap-2 pl-2">
        <button disabled={busy} onClick={() => onAutoChange(!auto)} className={cx(buttonStyles.secondary, "max-sm:flex-1")}>{auto ? "Pause" : "Start / Resume"}</button>
        <button disabled={busy} onClick={onTick} className={cx(buttonStyles.primary, "max-sm:flex-1")}>{busy && !resetting ? "Applying..." : "Run now"}</button>
        <button
          disabled={busy}
          onClick={() => {
            if (window.confirm("Reset the complete ReconMate demo simulation? This restores the original seeded portfolio, cycle 0, operating date, events, payments, promises, disputes, recovery work, and intelligence state.")) onReset();
          }}
          className={cx(buttonStyles.secondary, "border-rose-300/15 text-rose-100/75 hover:border-rose-300/35 hover:text-rose-50 max-sm:w-full")}
        >
          {resetting ? "Restoring baseline..." : "Reset demo"}
        </button>
      </div>
      {busy && <div className="mt-4 border-t border-sky-300/10 pl-2 pt-3" role="status"><p className="text-[11px] font-semibold text-sky-200">{resetting ? "Restoring the seeded portfolio and refreshing every operational view..." : "Persisting facts and synchronizing dashboard intelligence..."}</p></div>}
      {!busy && feedback && (
        <div className={cx("live-enter mt-4 border-t pl-2 pt-3", feedback.status === "REFRESH_FAILED" ? "border-amber-300/15" : "border-emerald-300/10")} role="status" aria-live="polite">
          <p className={cx("text-[11px] font-semibold", feedback.status === "REFRESH_FAILED" ? "text-amber-100" : "text-emerald-200")}>{feedback.headline}</p>
          <p className="mt-1 text-[10px] leading-4 text-slate-400">{feedback.event}</p>
          <p className={cx("mt-2 text-[11px] font-medium leading-4", feedback.status === "MATERIAL_CHANGE" ? "text-sky-200" : feedback.status === "REFRESH_FAILED" ? "text-amber-100/80" : "text-slate-300")}>{feedback.summary}</p>
          {feedback.transition && (
            <div className="mt-3 space-y-3 rounded-xl border border-white/[.07] bg-black/10 p-3">
              <div>
                <p className="text-[9px] font-bold uppercase tracking-[.11em] text-slate-500">{feedback.transition.entity_type === "CUSTOMER" ? "Customer portfolio assessment" : "Recovery case assessment"} / {feedback.transition.entity_name}</p>
                <p className="mt-1.5 text-sm font-semibold text-white">{feedback.transition.current_recommendation_title}</p>
                <p className="mt-1 text-[10px] leading-4 text-slate-400">{feedback.transition.current_recommendation_explanation}</p>
              </div>
              <div className="flex flex-wrap gap-2 text-[9px] font-bold uppercase tracking-[.1em]"><span className="rounded-full bg-white/[.05] px-2 py-1 text-slate-300">{feedback.transition.previous_risk_level ?? "New"} → {feedback.transition.current_risk_level}</span><span className="rounded-full bg-white/[.05] px-2 py-1 text-slate-300">Score {feedback.transition.previous_score ?? "-"} → {feedback.transition.current_score}</span></div>
              <TransitionDetail label="What changed" value={feedback.transition.what_changed} />
              <TransitionDetail label="Why intelligence changed" value={feedback.transition.why_intelligence_changed} />
              <TransitionDetail label="Decision impact" value={feedback.transition.decision_impact} />
              <TransitionDetail label="Why it matters" value={feedback.transition.operator_significance} />
              {feedback.transition.operator_next_step && <TransitionDetail label="Operator next step" value={feedback.transition.operator_next_step} />}
              {feedback.transition.workflow_effect && <TransitionDetail label="If the operator proceeds" value={feedback.transition.workflow_effect} />}
            </div>
          )}
          {feedback.changes.length > 0 && <ul className="mt-2 space-y-1 text-[10px] leading-4 text-slate-400">{feedback.changes.map((change) => <li key={change}>• {change}</li>)}</ul>}
        </div>
      )}
      {!busy && resetFeedback && (
        <div className={cx("live-enter mt-4 border-t pl-2 pt-3", resetFeedback.status === "SUCCESS" ? "border-emerald-300/10" : "border-amber-300/15")} role="status" aria-live="polite">
          <p className={cx("text-[11px] font-semibold leading-4", resetFeedback.status === "SUCCESS" ? "text-emerald-200" : "text-amber-100")}>{resetFeedback.message}</p>
        </div>
      )}
      <p className="mt-3 pl-2 text-[10px] leading-4 text-slate-600">Each completed cycle refreshes portfolio facts, recovery state, recommendations, and intelligence.</p>
    </section>
  );
}

function TransitionDetail({ label, value }: { label: string; value: string }) {
  return <div><p className="text-[9px] font-bold uppercase tracking-[.11em] text-slate-500">{label}</p><p className="mt-1 text-[10px] leading-4 text-slate-300">{value}</p></div>;
}
