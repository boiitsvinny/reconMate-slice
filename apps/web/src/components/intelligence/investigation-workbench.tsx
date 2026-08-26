"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { CommandResult, IntelligenceResult, PriorityLevel } from "@/lib/intelligence-api";
import { formatMoney } from "@/components/dashboard/data";
import { buttonStyles, Panel, SectionHeader, StatusPill } from "@/components/dashboard/ui";

const label = (value: string) => value.replaceAll("_", " ");
const tone = (level: PriorityLevel) => level === "CRITICAL" ? "rose" : level === "HIGH" ? "amber" : level === "MEDIUM" ? "sky" : "slate";

export function InvestigationWorkbench({ result, onOpenTarget }: { result: CommandResult; onOpenTarget?: (targetType: string, targetId: string) => void }) {
  if (!result.analyzed_entities.length) return null;
  return <div className="space-y-6">
    {result.analyzed_entities.length > 1 && <ComparisonPanel result={result} />}
    <Panel className="overflow-hidden">
      <SectionHeader eyebrow="Investigate further" title="How each decision was derived" detail="Scoped facts, deterministic score contributions, blockers, and current recommendations." prominent />
      <div className="divide-y divide-white/[.06]">{result.analyzed_entities.map((entity, index) => <EntityInspector key={entity.entity_type + "-" + entity.entity_id} entity={entity} rank={result.query_evidence.ranking.find((item) => item.entity_id === entity.entity_id)} open={result.analyzed_entities.length === 1 || index === 0} onOpenTarget={onOpenTarget} />)}</div>
    </Panel>
  </div>;
}

function EntityInspector({ entity, rank, open, onOpenTarget }: { entity: IntelligenceResult; rank?: CommandResult["query_evidence"]["ranking"][number]; open: boolean; onOpenTarget?: (targetType: string, targetId: string) => void }) {
  const actionability = actionabilityFor(entity);
  return <details className="group p-4 sm:p-5" open={open}>
    <summary className="flex cursor-pointer list-none flex-col gap-3 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300/40 sm:flex-row sm:items-center sm:justify-between">
      <div><p className="text-base font-semibold text-white">{entity.entity_name}</p><p className="mt-1 break-all text-[10px] text-slate-600">{label(entity.entity_type)} · {entity.entity_id}</p></div>
      <div className="flex flex-wrap items-center gap-2"><StatusPill tone={tone(entity.level)}>{entity.level} risk</StatusPill><span className="text-base font-semibold text-white">{entity.score}/100</span><span className="text-[13px] text-slate-300">{entity.recommendation.title}</span></div>
    </summary>
    <div className="mt-5 grid gap-px overflow-hidden rounded-xl border border-white/[.07] bg-white/[.07] sm:grid-cols-2 xl:grid-cols-4">
      <SemanticCell label="Current risk" value={entity.level} detail="Risk derived from the current factual score." />
      <SemanticCell label="Actionability" value={actionability.label} detail={actionability.detail} />
      <SemanticCell label="Current blocker" value={actionability.blocker || "None detected"} detail="A blocker can restrain action even when risk is high." />
      <SemanticCell label="Recommended action" value={entity.recommendation.title} detail="What ReconMate recommends from current facts." />
    </div>
    <div className="mt-5 grid gap-3 xl:grid-cols-[minmax(0,.9fr)_24px_minmax(0,1fr)_24px_minmax(0,1fr)_24px_minmax(0,1fr)] xl:items-stretch">
      <LineageStage eyebrow="Source facts" title="Persisted record facts" items={sourceFacts(entity)} footer={"Entity " + entity.entity_id.slice(0, 12) + " · evaluated " + new Date(entity.calculated_at).toLocaleDateString()} />
      <FlowArrow />
      <LineageStage eyebrow="Operational signals" title="Conditions derived" items={entity.signals.map((item) => item.title + ": " + item.explanation)} empty="No material risk signal is currently present." />
      <FlowArrow />
      <ScoreStage entity={entity} />
      <FlowArrow />
      <LineageStage eyebrow="Decision" title={entity.recommendation.title} items={[entity.recommendation.explanation, actionability.detail]} />
    </div>
    <div className="mt-4 grid gap-4 rounded-xl border border-amber-300/12 bg-amber-300/[.025] p-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
      <div><p className="text-[11px] font-bold uppercase tracking-[.12em] text-amber-200/80">What would change this decision?</p><p className="mt-2 text-xs leading-5 text-slate-400">These supported fact changes trigger a fresh deterministic evaluation; they do not guarantee a specific future score.</p><ul className="mt-2 grid gap-1.5 text-[13px] leading-5 text-slate-200 sm:grid-cols-2">{decisionBoundaries(entity).map((item) => <li key={item} className="flex gap-2"><span className="text-amber-300">•</span><span>{item}</span></li>)}</ul></div>
      <div className="flex flex-col gap-2 sm:flex-row"><Link href="/history" className={buttonStyles.secondary}>View underlying records</Link>{onOpenTarget && <button type="button" onClick={() => onOpenTarget(entity.entity_type, entity.entity_id)} className={buttonStyles.primary}>Review in workspace</button>}</div>
    </div>
    {rank?.stored_workflow_priority && <p className="mt-3 text-[10px] text-slate-500">Stored workflow priority: <strong className="text-slate-300">{label(rank.stored_workflow_priority)}</strong> · the priority already recorded in the operator workflow, shown separately from current intelligence.</p>}
  </details>;
}

function ScoreStage({ entity }: { entity: IntelligenceResult }) {
  return <article className="rounded-xl bg-[#08111f] p-4"><p className="text-[10px] font-bold uppercase tracking-[.14em] text-sky-300">Intelligence score</p><h4 className="mt-2 text-sm font-semibold text-white">Exact score construction</h4><div className="mt-3 space-y-2">{entity.factors.map((factor) => <div key={factor.type + "-" + factor.explanation} className="flex items-start justify-between gap-3 text-[13px]"><span className="leading-5 text-slate-300">{factor.title}</span><strong className="shrink-0 tabular-nums text-sky-200">+{factor.points}</strong></div>)}{!entity.factors.length && <p className="text-xs text-slate-500">No scoring factors contributed points.</p>}</div><div className="mt-4 border-t border-white/[.07] pt-3 text-[13px]"><div className="flex justify-between text-slate-400"><span>Raw weighted score</span><strong className="text-white">{entity.raw_score}</strong></div><div className="mt-2 flex justify-between text-slate-300"><span>Displayed score</span><strong className="text-sky-200">{entity.score}/100{entity.raw_score > 100 ? " · capped" : ""}</strong></div><div className="mt-2 flex justify-between text-slate-400"><span>Resulting severity</span><StatusPill tone={tone(entity.level)}>{entity.level}</StatusPill></div></div></article>;
}

function ComparisonPanel({ result }: { result: CommandResult }) {
  const entities = result.analyzed_entities;
  const [leftId, setLeftId] = useState(entities[0]?.entity_id || "");
  const [rightId, setRightId] = useState(entities[1]?.entity_id || entities[0]?.entity_id || "");
  useEffect(() => { setLeftId(entities[0]?.entity_id || ""); setRightId(entities[1]?.entity_id || entities[0]?.entity_id || ""); }, [result.plan_id, entities]);
  const left = entities.find((item) => item.entity_id === leftId) || entities[0];
  const right = entities.find((item) => item.entity_id === rightId) || entities[1];
  const explanation = useMemo(() => left && right ? comparisonExplanation(left, right, result) : { ranking: "", actionability: "" }, [left, right, result]);
  if (!left || !right) return null;
  return <Panel className="overflow-hidden"><SectionHeader eyebrow="Why one result ranks above another" title={"Compare " + left.entity_name + " with " + right.entity_name} detail="A factual comparison using only records returned by this command." prominent /><div className="grid gap-3 border-b border-white/[.06] p-4 sm:grid-cols-2"><CompareSelect label="First returned result" value={left.entity_id} entities={entities} onChange={setLeftId} /><CompareSelect label="Compare with" value={right.entity_id} entities={entities} onChange={setRightId} /></div><div className="grid gap-px bg-white/[.06] lg:grid-cols-2"><ComparisonSide entity={left} /><ComparisonSide entity={right} /></div><div className="space-y-3 border-t border-white/[.06] px-5 py-4 text-[13px] leading-5 text-slate-300"><p><span className="font-semibold text-sky-200">Ranking:</span> {explanation.ranking}</p><p><span className="font-semibold text-emerald-200">Operational actionability:</span> {explanation.actionability}</p>{result.query_evidence.ranking_policy.length > 0 && <p className="text-xs text-slate-500">Comparator: {result.query_evidence.ranking_policy.join(" → ")}.</p>}</div></Panel>;
}

function CompareSelect({ label: fieldLabel, value, entities, onChange }: { label: string; value: string; entities: IntelligenceResult[]; onChange: (value: string) => void }) {
  return <label className="text-[10px] font-bold uppercase tracking-[.12em] text-slate-500">{fieldLabel}<select value={value} onChange={(event) => onChange(event.target.value)} className="mt-2 w-full rounded-lg border border-white/[.1] bg-[#08111f] px-3 py-2 text-xs font-normal normal-case tracking-normal text-white">{entities.map((entity) => <option key={entity.entity_id} value={entity.entity_id}>{entity.entity_name}</option>)}</select></label>;
}

function ComparisonSide({ entity }: { entity: IntelligenceResult }) {
  const actionability = actionabilityFor(entity);
  return <article className="bg-[#08111f] p-5"><div className="flex items-start justify-between gap-3"><div><h3 className="text-base font-semibold text-white">{entity.entity_name}</h3><p className="mt-1 text-xs text-slate-400">{formatMoney(entity.metrics.overdue_exposure)} overdue · {entity.metrics.max_days_overdue} days</p></div><StatusPill tone={tone(entity.level)}>{entity.level} risk</StatusPill></div><dl className="mt-5 grid grid-cols-2 gap-4 text-xs sm:grid-cols-3"><QueryFact term="Displayed score" value={`${entity.score}/100`} /><QueryFact term="Raw score" value={String(entity.raw_score)} /><QueryFact term="Risk band" value={entity.level} /><QueryFact term="Overdue exposure" value={formatMoney(entity.metrics.overdue_exposure)} /><QueryFact term="Oldest overdue" value={`${entity.metrics.max_days_overdue} days`} /><QueryFact term="Payment recency" value={entity.metrics.days_since_last_payment === null ? "No payment recorded" : `${entity.metrics.days_since_last_payment} days ago`} /><QueryFact term="Broken promises" value={String(entity.metrics.broken_promise_count)} /><QueryFact term="Active promises" value={String(entity.metrics.active_promise_count)} /><QueryFact term="Active disputes" value={String(entity.metrics.active_dispute_count)} /><QueryFact term="Actionability" value={actionability.label} /><QueryFact term="Blocker" value={actionability.blocker ?? "None detected"} /><QueryFact term="Recommendation" value={entity.recommendation.title} /></dl></article>;
}

function comparisonExplanation(left: IntelligenceResult, right: IntelligenceResult, result: CommandResult) {
  const query = result.interpreted_intent.query;
  const values = {
    RISK_SCORE: [left.score, right.score, "current intelligence score"],
    TOTAL_EXPOSURE: [Number(left.metrics.total_outstanding_amount), Number(right.metrics.total_outstanding_amount), "total exposure"],
    OVERDUE_EXPOSURE: [Number(left.metrics.overdue_exposure), Number(right.metrics.overdue_exposure), "overdue exposure"],
    DAYS_OVERDUE: [left.metrics.max_days_overdue, right.metrics.max_days_overdue, "oldest invoice age"],
    LAST_PAYMENT: [left.metrics.days_since_last_payment === null ? 10 ** 9 : left.metrics.days_since_last_payment, right.metrics.days_since_last_payment === null ? 10 ** 9 : right.metrics.days_since_last_payment, "payment inactivity"],
  } as const;
  const [leftValue, rightValue, basis] = values[query.sort_by];
  const ranks = new Map(result.query_evidence.ranking.map((item) => [item.entity_id, item.rank]));
  const leftFirst = (ranks.get(left.entity_id) ?? Number.MAX_SAFE_INTEGER) < (ranks.get(right.entity_id) ?? Number.MAX_SAFE_INTEGER);
  const higher = leftFirst ? left : right;
  const lower = leftFirst ? right : left;
  const primaryDifferent = leftValue !== rightValue;
  let ranking: string;
  if (primaryDifferent) {
    ranking = `${higher.entity_name} ranks first because the query orders by ${query.descending ? "highest" : "lowest"} ${basis}; the compared values are ${formatComparisonValue(query.sort_by, leftValue)} and ${formatComparisonValue(query.sort_by, rightValue)}.`;
  } else if (left.raw_score !== right.raw_score) {
    const capped = left.score === 100 && right.score === 100;
    ranking = `${capped ? "Both accounts display 100/100 because their scores are capped. " : "The primary displayed scores are tied. "}${higher.entity_name} ranks above ${lower.entity_name} because its raw intelligence score is ${higher.raw_score} versus ${lower.raw_score}.`;
  } else if (left.metrics.overdue_exposure !== right.metrics.overdue_exposure) {
    ranking = `The primary value and raw score are tied. ${higher.entity_name} ranks above ${lower.entity_name} on overdue exposure: ${formatMoney(higher.metrics.overdue_exposure)} versus ${formatMoney(lower.metrics.overdue_exposure)}.`;
  } else if (left.metrics.max_days_overdue !== right.metrics.max_days_overdue) {
    ranking = `The primary value, raw score, and overdue exposure are tied. ${higher.entity_name} ranks above ${lower.entity_name} because its oldest overdue balance is ${higher.metrics.max_days_overdue} days versus ${lower.metrics.max_days_overdue}.`;
  } else {
    ranking = "All financial ranking fields are tied; the stable entity identifier provides deterministic final ordering.";
  }
  const leftAction = actionabilityFor(left);
  const rightAction = actionabilityFor(right);
  const actionability = `${left.entity_name} is ${leftAction.label.toLowerCase()}${leftAction.blocker ? ` because ${leftAction.blocker.toLowerCase()}` : " with no current blocker"}; ${right.entity_name} is ${rightAction.label.toLowerCase()}${rightAction.blocker ? ` because ${rightAction.blocker.toLowerCase()}` : " with no current blocker"}.`;
  return { ranking, actionability };
}

function formatComparisonValue(sort: CommandResult["interpreted_intent"]["query"]["sort_by"], value: number) {
  if (sort === "LAST_PAYMENT" && value === 10 ** 9) return "no payment recorded";
  return sort === "TOTAL_EXPOSURE" || sort === "OVERDUE_EXPOSURE" ? formatMoney(value) : String(value);
}

function actionabilityFor(entity: IntelligenceResult) {
  if (entity.metrics.active_dispute_count) return { label: "Blocked", blocker: "Active dispute requires review", detail: "Recovery action is restrained until the recorded dispute is reviewed." };
  if (entity.metrics.active_promise_count) return { label: "Waiting", blocker: "Valid payment promise is active", detail: "ReconMate is monitoring the promise deadline before another recovery action." };
  if (entity.recommendation.action === "MONITOR") return { label: "Monitoring", blocker: null, detail: "No current condition requires operator intervention." };
  return { label: "Actionable", blocker: null, detail: "Current facts support operator review through the controlled workflow." };
}

function decisionBoundaries(entity: IntelligenceResult) {
  if (entity.recommendation.action === "REVIEW_DISPUTE") return ["The active dispute is resolved or no longer blocks the outstanding invoice.", "A payment changes the outstanding exposure being disputed."];
  if (entity.recommendation.action === "WAIT_FOR_PROMISE") return ["The active promise expires without matching payment evidence.", "The promise is fulfilled, cancelled, or replaced by a new recorded commitment."];
  if (entity.recommendation.action === "MONITOR") return ["Receivables become overdue or payment activity stalls.", "A promise breaks, a dispute opens, or recovery work becomes stalled."];
  return ["A valid payment promise is recorded and takes precedence over recovery action.", "An active dispute is recorded and requires review.", "Payment materially reduces or clears the overdue exposure and its score factors."];
}

function sourceFacts(entity: IntelligenceResult) {
  const metrics = entity.metrics;
  return [
    String(metrics.overdue_invoice_count) + " overdue invoice(s) · " + formatMoney(metrics.overdue_exposure) + " exposure",
    "Oldest overdue balance: " + metrics.max_days_overdue + " days",
    metrics.broken_promise_count + " broken and " + metrics.active_promise_count + " active promise(s)",
    metrics.active_dispute_count + " active dispute(s)",
    metrics.days_since_last_payment === null ? "No payment activity recorded" : "Last payment activity: " + metrics.days_since_last_payment + " days ago",
  ];
}

function LineageStage({ eyebrow, title, items, empty, footer }: { eyebrow: string; title: string; items: string[]; empty?: string; footer?: string }) {
  return <article className="rounded-xl bg-[#08111f] p-4"><p className="text-[10px] font-bold uppercase tracking-[.14em] text-sky-300">{eyebrow}</p><h4 className="mt-2 text-sm font-semibold text-white">{title}</h4>{items.length ? <ul className="mt-3 space-y-2 text-xs leading-5 text-slate-300">{items.slice(0, 5).map((item) => <li key={item} className="flex gap-2"><span className="text-sky-300">•</span><span>{item}</span></li>)}</ul> : <p className="mt-3 text-xs text-slate-500">{empty}</p>}{footer && <p className="mt-3 border-t border-white/[.06] pt-3 text-[10px] text-slate-500">{footer}</p>}</article>;
}

function FlowArrow() {
  return <div className="flex items-center justify-center text-sky-300/50" aria-hidden="true"><span className="xl:hidden">↓</span><span className="hidden xl:inline">→</span></div>;
}

function SemanticCell({ label: fieldLabel, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="bg-[#08111f] p-4"><p className="text-[10px] font-bold uppercase tracking-[.12em] text-slate-400">{fieldLabel}</p><p className="mt-2 text-sm font-semibold text-white">{value}</p><p className="mt-1 text-xs leading-5 text-slate-400">{detail}</p></div>;
}

function QueryFact({ term, value }: { term: string; value: string }) {
  return <div><dt className="text-[9px] uppercase tracking-[.1em] text-slate-600">{term}</dt><dd className="mt-1 text-slate-300">{value}</dd></div>;
}
