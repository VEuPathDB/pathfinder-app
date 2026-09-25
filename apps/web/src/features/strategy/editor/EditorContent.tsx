"use client";

import { useState } from "react";
import { useStore } from "@tanstack/react-form";
import { toast } from "sonner";
import type { Step } from "@pathfinder/shared";
import { isInputStepParam } from "@/features/strategy/parameters/spec";
import { useStrategyGraphCtx } from "@/features/strategy/graph/StrategyGraphContext";
import {
  useDuplicateStepMutation,
  useUpdateStepMutation,
} from "@/features/strategy/mutations";
import { useSaveSubstrategyMutation } from "@/features/strategy/mutations/useSaveSubstrategyMutation";
import { SaveSubstrategyDialog } from "./SaveSubstrategyDialog";
import { useStrategyData } from "@/lib/api/strategy";
import { strategyStepUrl } from "@/lib/routes";
import { useStepSnapshot } from "@/state/strategy/useStepSnapshot";
import { EditorHeader } from "./EditorHeader";
import { EditorBody } from "./EditorBody";
import { EditorFooter, type SyncState } from "./EditorFooter";
import { StepResults } from "./StepResults";
import { DiscardConfirmDialog } from "./DiscardConfirmDialog";
import { RecoveryBanner } from "./RecoveryBanner";
import { useStepEditorState } from "./useStepEditorState";
import type { ParamFormValues } from "./hooks/useParamForm";
import { useStepDraftChanges } from "./hooks/useStepDraftChanges";
import {
  useRecoveredDraft,
  useStepDraftPersistence,
  type StepDraftValues,
} from "./hooks/useStepDraftPersistence";
import { buildStepPatch } from "./buildStepPatch";
import { DEFAULT_COLOCATION } from "./schema/colocationSchema";

export type CloseHandler = () => Promise<void>;

interface EditorContentProps {
  step: Step;
  siteId: string;
  recordType: string | null;
  conversationId: string;
  registerCloseHandler: (handler: CloseHandler) => void;
  onClosed: () => void;
}

function snapshotFormValues(values: Record<string, unknown>): StepDraftValues {
  return { ...values };
}

export function EditorContent({
  step,
  siteId,
  recordType,
  conversationId,
  registerCloseHandler,
  onClosed,
}: EditorContentProps) {
  const state = useStepEditorState({ step, siteId, recordType });
  const { requestDelete } = useStrategyGraphCtx();
  const duplicateStep = useDuplicateStepMutation(conversationId);
  const updateStep = useUpdateStepMutation(conversationId);
  const saveSubstrategy = useSaveSubstrategyMutation({ conversationId, siteId });
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const stepNumber = useStepNumber(conversationId, step.id);
  const wdkUrl = useStrategyData(conversationId)?.wdkUrl ?? null;
  const snapshot = useStepSnapshot(step);

  const persistence = useStepDraftPersistence({
    strategyId: conversationId,
    stepId: step.id,
  });

  const allowedParamKeys = new Set(
    state.paramSpecs
      .filter((s) => s.name !== "" && s.isVisible !== false && !isInputStepParam(s))
      .map((s) => s.name),
  );

  const formValues = useStore(state.form.store, (s) => s.values);

  const baselineDraftValues: StepDraftValues = {};
  for (const key of allowedParamKeys) {
    baselineDraftValues[key] = formValues[key] ?? "";
  }

  const recovered = useRecoveredDraft({
    strategyId: conversationId,
    stepId: step.id,
    baselineValues: state.paramFormHydrated ? baselineDraftValues : {},
  });

  const changes = useStepDraftChanges({
    step,
    formValues,
    operator: state.operatorValue,
    displayName: state.name ?? "",
    colocationParams: state.colocationParams ?? null,
    allowedParamKeys,
  });

  const [confirmDiscardOpen, setConfirmDiscardOpen] = useState(false);

  const writeDraftSnapshot = (): void => {
    if (!state.paramFormHydrated) return;
    persistence.scheduleWrite(snapshotFormValues(state.form.state.values));
  };

  const buildPatch = (): Partial<Step> =>
    buildStepPatch({
      step,
      formValues,
      hiddenDefaults: state.hiddenDefaults,
      allowedParamKeys,
      paramSpecs: state.paramSpecs,
      operator: state.operatorValue,
      displayName: state.name ?? "",
      colocationParams: state.colocationParams ?? null,
    });

  const commitNow = async (): Promise<boolean> => {
    if (!changes.hasChanges) return true;
    try {
      await updateStep.mutateAsync({ stepId: step.id, patch: buildPatch() });
      persistence.clear();
      return true;
    } catch {
      return false;
    }
  };

  registerCloseHandler(async () => {
    const ok = await commitNow();
    if (ok) onClosed();
  });

  const handleDiscardConfirmed = (): void => {
    state.form.reset();
    state.setName(step.displayName);
    state.setOperatorValue(step.operator ?? "");
    state.setColocationParams(step.colocationParams);
    persistence.clear();
    setConfirmDiscardOpen(false);
  };

  const handleRename = (next: string): void => {
    state.setName(next);
    writeDraftSnapshot();
  };

  const handleDelete = (): void => {
    persistence.clear();
    requestDelete(step.id);
    onClosed();
  };

  const handleDuplicate = (): void => {
    duplicateStep.mutate({ stepId: step.id });
  };

  const handleSaveAsReusable = (): void => {
    setSaveDialogOpen(true);
  };

  const handleConfirmSave = (input: { name: string; description: string }): void => {
    saveSubstrategy.mutate(
      {
        stepId: step.id,
        name: input.name,
        description: input.description === "" ? null : input.description,
      },
      { onSuccess: () => setSaveDialogOpen(false) },
    );
  };

  const handleCopyUrl = (): void => {
    if (typeof window === "undefined") return;
    const origin = window.location.origin;
    const url = `${origin}${strategyStepUrl(siteId, conversationId, step.id)}`;
    void navigator.clipboard.writeText(url);
    toast.success("Step URL copied");
  };

  const handleSearchChange = (next: string | null): void => {
    if (next === null || next === step.searchName) return;
    state.setEditableSearchName(next);
    const picked = state.searchOptions.find((s) => s.name === next);
    const nextRecordType = picked?.recordType ?? step.recordType ?? null;
    const patch: Partial<Step> = { searchName: next };
    if (nextRecordType !== null) {
      patch.recordType = nextRecordType;
    }
    persistence.clear();
    updateStep.mutate({ stepId: step.id, patch });
  };

  const handleOperatorChange = (operator: string): void => {
    if (operator === state.operatorValue) return;
    state.setOperatorValue(operator);
    if (operator === "COLOCATE") {
      const next = state.colocationParams ?? DEFAULT_COLOCATION;
      state.setColocationParams(next);
    } else {
      state.setColocationParams(null);
    }
    writeDraftSnapshot();
  };

  const handleColocationChange = (
    next: NonNullable<Step["colocationParams"]>,
  ): void => {
    state.setColocationParams(next);
    writeDraftSnapshot();
  };

  const handleFieldChanged = (name: string, allValues: ParamFormValues): void => {
    state.onDependentFieldChange(name, allValues);
    writeDraftSnapshot();
  };

  const handleFieldBlurred = (): void => {
    persistence.flush();
  };

  const handleRestoreDraft = (): void => {
    if (recovered.draft === null) return;
    for (const [key, val] of Object.entries(recovered.draft)) {
      if (!allowedParamKeys.has(key)) continue;
      state.form.setFieldValue(key, val as string | string[]);
    }
    recovered.dismiss();
  };

  const syncState = computeSyncState({
    updatePending: updateStep.isPending,
    updateError: updateStep.isError,
  });

  const footerProps = {
    syncState,
    changeCount: changes.changeCount,
    isSaving: updateStep.isPending,
    onSave: () => {
      void commitNow();
    },
    onDiscard: () => setConfirmDiscardOpen(true),
    count: snapshot.estimatedSize,
    recordType: step.recordType,
    wdkUrl,
    siteId,
  };

  return (
    <div className="flex h-full flex-col">
      <EditorHeader
        step={step}
        kind={state.kind}
        stepNumber={stepNumber}
        onRename={handleRename}
        onDelete={handleDelete}
        onDuplicate={handleDuplicate}
        onCopyUrl={handleCopyUrl}
        onSaveAsReusable={handleSaveAsReusable}
      />
      {recovered.draft !== null && (
        <RecoveryBanner onRestore={handleRestoreDraft} onDismiss={recovered.dismiss} />
      )}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        <EditorBody
          state={state}
          step={step}
          onSearchChange={handleSearchChange}
          onOperatorChange={handleOperatorChange}
          onColocationChange={handleColocationChange}
          onFieldChanged={handleFieldChanged}
          onFieldBlurred={handleFieldBlurred}
        />
        <StepResults
          conversationId={conversationId}
          stepId={step.id}
          wdkStepId={step.wdkStepId}
          siteId={siteId}
          estimatedSize={footerProps.count}
          hasUnsavedEdits={footerProps.changeCount > 0}
          rationale={step.rationale ?? null}
        />
      </div>
      <EditorFooter {...footerProps} />
      <DiscardConfirmDialog
        open={confirmDiscardOpen}
        onOpenChange={setConfirmDiscardOpen}
        changeCount={changes.changeCount}
        onConfirm={handleDiscardConfirmed}
      />
      <SaveSubstrategyDialog
        open={saveDialogOpen}
        onOpenChange={setSaveDialogOpen}
        defaultName={step.displayName ?? step.searchName ?? "Saved strategy"}
        isSaving={saveSubstrategy.isPending}
        onConfirm={handleConfirmSave}
      />
    </div>
  );
}

function computeSyncState(args: {
  updatePending: boolean;
  updateError: boolean;
}): SyncState {
  if (args.updatePending) return "saving";
  if (args.updateError) return "error";
  return "idle";
}

function useStepNumber(conversationId: string, stepId: string): number | null {
  const steps = useStrategyData(conversationId)?.steps ?? [];
  const idx = steps.findIndex((s) => s.id === stepId);
  return idx >= 0 ? idx + 1 : null;
}
