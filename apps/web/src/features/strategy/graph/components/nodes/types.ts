import type { Step } from "@pathfinder/shared";

export type StepNodeData = {
  step: Step;
  isOrphan?: boolean | undefined;
  showOutputHandle?: boolean | undefined;
  showPrimaryInputHandle?: boolean | undefined;
  showSecondaryInputHandle?: boolean | undefined;
  enterDelayIndex?: number | undefined;
  onOpenDetails?: ((stepId: string) => void) | undefined;
  onRename?: ((stepId: string, nextName: string) => void) | undefined;
  onDuplicate?: ((stepId: string) => void) | undefined;
  onDelete?: ((stepId: string) => void) | undefined;
};

export type StepNodeProps = {
  step: Step;
  selected: boolean;
  isOrphan?: boolean | undefined;
  showOutputHandle?: boolean | undefined;
  showPrimaryInputHandle?: boolean | undefined;
  showSecondaryInputHandle?: boolean | undefined;
  enterDelayIndex?: number | undefined;
  onOpenDetails?: ((stepId: string) => void) | undefined;
  onRename?: ((stepId: string, nextName: string) => void) | undefined;
  onDuplicate?: ((stepId: string) => void) | undefined;
  onDelete?: ((stepId: string) => void) | undefined;
};
