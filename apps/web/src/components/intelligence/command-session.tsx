"use client";

import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ActionOutcome,
  ApiRequestError,
  CommandRequest,
  CommandResult,
  ConfirmationResult,
  confirmCommand,
  ProposalStatus,
  submitCommand,
} from "@/lib/intelligence-api";

export const PROCESSING_STAGES = [
  "Understanding request",
  "Checking operational intelligence",
  "Reviewing affected records",
  "Evaluating current recovery state",
  "Building action plan",
] as const;

export type CommandActivity = {
  planId: string;
  command: string;
  timestamp: string;
  intent: string;
  summary: string;
  analyzedCount: number;
  proposalCount: number;
  status: "COMPLETED" | "PREPARED" | "AWAITING_CONFIRMATION" | "EXECUTED" | "FAILED";
};

type CommandSession = {
  activeCommand: string;
  result: CommandResult | null;
  processing: boolean;
  confirming: boolean;
  processingStage: number;
  error: string | null;
  history: CommandActivity[];
  runCommand: (request: CommandRequest) => Promise<CommandResult | null>;
  confirmPlan: (proposalIds: string[]) => Promise<ConfirmationResult | null>;
  clearError: () => void;
  clearSession: () => void;
};

const CommandSessionContext = createContext<CommandSession | null>(null);

export function CommandSessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [activeCommand, setActiveCommand] = useState("");
  const [result, setResult] = useState<CommandResult | null>(null);
  const [processingStage, setProcessingStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<CommandActivity[]>([]);

  const commandMutation = useMutation({ mutationFn: submitCommand });
  const confirmationMutation = useMutation({
    mutationFn: ({ planId, proposalIds }: { planId: string; proposalIds: string[] }) => confirmCommand(planId, proposalIds),
  });

  useEffect(() => {
    if (!commandMutation.isPending) return;
    const timer = window.setInterval(() => {
      setProcessingStage((current) => Math.min(current + 1, PROCESSING_STAGES.length - 1));
    }, 350);
    return () => window.clearInterval(timer);
  }, [commandMutation.isPending]);

  const runCommand = useCallback(async (request: CommandRequest) => {
    const command = request.command.trim();
    if (!command || commandMutation.isPending) return null;
    setActiveCommand(command);
    setResult(null);
    setProcessingStage(0);
    setError(null);
    try {
      const next = await commandMutation.mutateAsync({ ...request, command });
      setResult(next);
      const confirmationCount = next.outcomes.filter((item) => item.status === "AWAITING_CONFIRMATION").length;
      const preparedCount = next.outcomes.filter((item) => item.status === "PREPARED").length;
      const activity: CommandActivity = {
        planId: next.plan_id,
        command,
        timestamp: next.audit.timestamp,
        intent: next.interpreted_intent.intent,
        summary: next.understanding_summary,
        analyzedCount: next.analyzed_entities.length,
        proposalCount: next.plan.proposed_actions.length,
        status: confirmationCount ? "AWAITING_CONFIRMATION" : preparedCount ? "PREPARED" : "COMPLETED",
      };
      setHistory((items) => [activity, ...items].slice(0, 12));
      return next;
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "The command could not be processed.";
      setError(message);
      const activity: CommandActivity = {
        planId: `failed-${Date.now()}`,
        command,
        timestamp: new Date().toISOString(),
        intent: "REQUEST_FAILED",
        summary: message,
        analyzedCount: 0,
        proposalCount: 0,
        status: "FAILED",
      };
      setHistory((items) => [activity, ...items].slice(0, 12));
      return null;
    }
  }, [commandMutation]);

  const confirmPlan = useCallback(async (proposalIds: string[]) => {
    if (!result || confirmationMutation.isPending || !proposalIds.length) return null;
    setError(null);
    try {
      const confirmation = await confirmationMutation.mutateAsync({ planId: result.plan_id, proposalIds });
      const returned = new Map(confirmation.outcomes.map((item) => [item.proposal_id, item]));
      setResult((current) => current ? {
        ...current,
        plan: { ...current.plan, requires_confirmation: false, execution_mode: confirmation.execution_mode },
        outcomes: current.outcomes.map((item): ActionOutcome => {
          const updated = returned.get(item.proposal_id);
          if (updated) return updated;
          if (item.status === "AWAITING_CONFIRMATION") {
            return { ...item, status: "NOT_EXECUTABLE" as ProposalStatus, message: "Not selected before the one-time plan was consumed." };
          }
          return item;
        }),
        warnings: [...current.warnings, ...confirmation.warnings],
      } : current);
      const executed = confirmation.outcomes.filter((item) => item.status === "EXECUTED").length;
      setHistory((items) => items.map((item) => item.planId === result.plan_id ? {
        ...item,
        status: executed ? "EXECUTED" : "FAILED",
        summary: executed ? `${executed} internal workflow action${executed === 1 ? "" : "s"} created after confirmation.` : "No workflow action was created.",
      } : item));
      await queryClient.invalidateQueries({ queryKey: ["reconmate"] });
      return confirmation;
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "The command plan could not be confirmed.";
      setError(message);
      if (caught instanceof ApiRequestError && (caught.status === 404 || caught.status === 410)) {
        setResult((current) => current ? {
          ...current,
          plan: { ...current.plan, requires_confirmation: false },
          outcomes: current.outcomes.map((item) => item.status === "AWAITING_CONFIRMATION" ? {
            ...item,
            status: "NOT_EXECUTABLE",
            message: caught.status === 410 ? "This confirmation plan expired. Run the command again to evaluate current data." : "This single-use plan is unavailable or was already confirmed.",
          } : item),
        } : current);
      }
      return null;
    }
  }, [confirmationMutation, queryClient, result]);

  const clearSession = useCallback(() => {
    setActiveCommand("");
    setResult(null);
    setProcessingStage(0);
    setError(null);
    setHistory([]);
    commandMutation.reset();
    confirmationMutation.reset();
  }, [commandMutation, confirmationMutation]);

  const value = useMemo<CommandSession>(() => ({
    activeCommand,
    result,
    processing: commandMutation.isPending,
    confirming: confirmationMutation.isPending,
    processingStage,
    error,
    history,
    runCommand,
    confirmPlan,
    clearError: () => setError(null),
    clearSession,
  }), [activeCommand, commandMutation.isPending, confirmationMutation.isPending, processingStage, error, history, result, runCommand, confirmPlan, clearSession]);

  return <CommandSessionContext.Provider value={value}>{children}</CommandSessionContext.Provider>;
}

export function useCommandSession(): CommandSession {
  const value = useContext(CommandSessionContext);
  if (!value) throw new Error("useCommandSession must be used within CommandSessionProvider.");
  return value;
}
