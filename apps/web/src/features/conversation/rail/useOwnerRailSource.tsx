"use client";

import type { Strategy } from "@strategist/shared";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { beginConversation } from "@/features/conversation/api/beginConversation";
import { InsertSavedDialog } from "@/features/saved/InsertSavedDialog";
import { SaveSubstrategyDialog } from "@/features/strategy/editor/SaveSubstrategyDialog";
import { useDeleteOperation } from "@/features/strategy/graph/hooks/useDeleteOperation";
import { useRefreshStepCountsMutation } from "@/features/strategy/mutations/useRefreshStepCountsMutation";
import { useSaveSubstrategyMutation } from "@/features/strategy/mutations/useSaveSubstrategyMutation";
import { edaTabUrl, strategyCanvasUrl, strategyStepUrl } from "@/lib/routes";
import { useEdaStore } from "@/state/eda";
import { useConversationExists } from "@/state/useConversationExists";
import { useRightRailStore } from "@/state/useRightRailStore";

import { isActiveTask, tasksListOptions } from "../api/tasks";
import type { RailSource, StrategyActions } from "./railSource";

const NO_PRIVATE_INPUTS: RailSource["privateInputs"] = {};

function useStrategyActions(
  conversationId: string,
  strategy: Strategy | null,
  siteId: string,
): StrategyActions {
  const router = useRouter();
  const [saveStepId, setSaveStepId] = useState<string | null>(null);
  const [insertTargetId, setInsertTargetId] = useState<string | null>(null);
  const [insertAsRoot, setInsertAsRoot] = useState(false);
  const saveMutation = useSaveSubstrategyMutation({
    conversationId: strategy?.id ?? "",
    siteId,
    onSuccess: () => setSaveStepId(null),
  });
  const deleteOperation = useDeleteOperation(strategy?.id ?? conversationId);
  const refreshCounts = useRefreshStepCountsMutation({
    conversationId: strategy?.id ?? "",
    siteId,
  });
  const saveTargetStep =
    saveStepId != null
      ? (strategy?.steps.find((s) => s.id === saveStepId) ?? null)
      : null;

  return {
    openEditor: () => {
      if (strategy != null) router.push(strategyCanvasUrl(strategy.id));
    },
    openStep: (stepId) => {
      if (strategy != null) router.push(strategyStepUrl(strategy.id, stepId));
    },
    refresh: { run: () => refreshCounts.mutate(), pending: refreshCounts.isPending },
    saveStep: setSaveStepId,
    insertSavedAt: setInsertTargetId,
    insertSavedAsRoot: () => setInsertAsRoot(true),
    removeSteps: (stepIds) =>
      deleteOperation.requestDeleteMany(stepIds, { skipConfirm: true }),
    dialogs: (
      <>
        {insertAsRoot && (
          <InsertSavedDialog
            open
            onOpenChange={(o) => {
              if (!o) setInsertAsRoot(false);
            }}
            conversationId={conversationId}
            siteId={siteId}
            targetStepId=""
            beginThread={() => beginConversation(conversationId, { siteId })}
          />
        )}
        {strategy != null && (
          <>
            <SaveSubstrategyDialog
              open={saveStepId != null}
              onOpenChange={(o) => {
                if (!o) setSaveStepId(null);
              }}
              defaultName={
                saveTargetStep?.displayName ??
                saveTargetStep?.searchName ??
                "Saved strategy"
              }
              isSaving={saveMutation.isPending}
              onConfirm={(input) => {
                if (saveStepId == null) return;
                saveMutation.mutate({
                  stepId: saveStepId,
                  name: input.name,
                  description: input.description === "" ? null : input.description,
                });
              }}
            />
            <InsertSavedDialog
              open={insertTargetId != null}
              onOpenChange={(o) => {
                if (!o) setInsertTargetId(null);
              }}
              conversationId={strategy.id}
              siteId={siteId}
              targetStepId={insertTargetId ?? ""}
              beginThread={() => beginConversation(strategy.id, { siteId })}
            />
          </>
        )}
      </>
    ),
  };
}

export function useOwnerRailSource({
  conversationId,
  strategy,
  siteId,
}: {
  conversationId: string;
  strategy: Strategy | null;
  siteId: string;
}): RailSource {
  const router = useRouter();
  const exists = useConversationExists(conversationId);
  const reviewOpen = useRightRailStore((s) => s.openPanel === "review");
  const tasks =
    useQuery({ ...tasksListOptions(conversationId), enabled: exists && reviewOpen })
      .data?.tasks ?? [];
  const study = useEdaStore((s) => s.analysis);
  const strategyActions = useStrategyActions(conversationId, strategy, siteId);
  return {
    key: conversationId,
    siteId,
    strategy,
    privateInputs: NO_PRIVATE_INPUTS,
    study,
    activeTasks: tasks.filter((t) => isActiveTask(t.status)),
    owner: {
      conversationId,
      strategy: strategyActions,
      openStudy: () => router.push(edaTabUrl(conversationId)),
    },
  };
}
