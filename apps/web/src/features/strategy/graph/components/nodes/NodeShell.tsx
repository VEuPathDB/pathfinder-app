"use client";

import { motion } from "motion/react";
import type { Step } from "@pathfinder/shared";
import { cn } from "@/lib/utils/cn";
import { useEntrance } from "@/lib/motion";
import { STAGGER_DELAY_MS } from "@/features/strategy/graph/motion";
import {
  reasonDetail,
  stepReason,
  stepSubtitle,
  stepTitle,
} from "@/features/strategy/graph/utils/stepTitle";
import { HoverActions } from "./HoverActions";
import { InlineRename } from "./InlineRename";
import { ResultLabel } from "./ResultLabel";
import { ValidationBanner } from "./ValidationBanner";
import type { StepSnapshot } from "@/state/strategy/useStepSnapshot";

export type NodeKind = "search" | "combine" | "transform";

type NodeShellProps = {
  kind: NodeKind;
  step: Step;
  selected: boolean;
  isOrphan?: boolean | undefined;
  width: number;
  height: number;
  snapshot: StepSnapshot;
  enterDelayIndex?: number | undefined;
  onOpenDetails?: ((stepId: string) => void) | undefined;
  onRename?: ((stepId: string, nextName: string) => void) | undefined;
  onDuplicate?: ((stepId: string) => void) | undefined;
  onDelete?: ((stepId: string) => void) | undefined;
  /** Optional clip-path applied to the surface (for chevron-shaped nodes). */
  surfaceClipPath?: string | undefined;
  /** Optional `data-clip` attr to make the clipped surface findable in tests. */
  surfaceClipDataAttr?: string | undefined;
  /** Slot for kind-specific body content (e.g. CombineNode renders the venn here). */
  children?: React.ReactNode | undefined;
  /** Slot for kind-specific handles (rendered before the chrome so they layer correctly). */
  handles?: React.ReactNode | undefined;
};

const KIND_VAR: Record<NodeKind, string> = {
  search: "leaf",
  combine: "combine",
  transform: "transform",
};

const KIND_DOT_LABEL: Record<NodeKind, string> = {
  search: "Search step",
  combine: "Combine step",
  transform: "Transform step",
};

export function NodeShell({
  kind,
  step,
  selected,
  isOrphan = false,
  width,
  height,
  snapshot,
  enterDelayIndex,
  onOpenDetails,
  onRename,
  onDuplicate,
  onDelete,
  surfaceClipPath,
  surfaceClipDataAttr,
  children,
  handles,
}: NodeShellProps) {
  const hasError =
    snapshot.isInvalid || snapshot.isFailed || snapshot.wdkPushError != null;
  const name = stepTitle(step, kind);
  const subtitle = stepSubtitle(step, kind);
  const reason = stepReason(step, kind);
  const isSyncing = snapshot.isBusy;
  const variantSlug = KIND_VAR[kind];
  const surfaceStyle: React.CSSProperties = {
    width,
    height,
    background: `linear-gradient(180deg, hsl(var(--card)) 0%, var(--kind-${variantSlug}-soft) 100%)`,
    borderColor: `var(--kind-${variantSlug}-ring)`,
    boxShadow: selected
      ? `0 0 0 2.5px hsl(var(--accent)), var(--shadow-card)`
      : "var(--shadow-card)",
    transition: "transform 180ms ease-out, box-shadow 180ms ease-out",
    ...(surfaceClipPath != null ? { clipPath: surfaceClipPath } : {}),
  };

  const surfaceClasses = cn(
    "relative rounded-[10px] border",
    !hasError && "hover:-translate-y-px hover:shadow-md",
    hasError && "border-l-[3px] !border-l-destructive",
    isSyncing && "node-syncing-pulse",
    isOrphan && "border-dashed !border-warning/60",
  );

  function handleRenameCommit(next: string) {
    if (onRename == null) return;
    const trimmed = next.trim();
    if (trimmed === "" || trimmed === name) return;
    onRename(step.id, trimmed);
  }

  const safeIndex =
    enterDelayIndex != null && enterDelayIndex >= 0 ? enterDelayIndex : 0;
  const entrance = useEntrance({
    initial: { opacity: 0, y: 6 },
    transition: {
      delay: safeIndex * (STAGGER_DELAY_MS / 1000),
      duration: 0.2,
      ease: "easeOut",
    },
  });

  return (
    <motion.div
      data-testid={`rf-node-${step.id}`}
      data-kind={kind}
      data-selected={selected ? "true" : "false"}
      data-validation={hasError ? "error" : undefined}
      data-syncing={isSyncing ? "true" : "false"}
      data-orphan={isOrphan ? "true" : "false"}
      data-enter-delay-index={safeIndex}
      className={cn("group relative", isOrphan && "opacity-70")}
      style={{ width, height }}
      {...entrance}
      animate={{ opacity: 1, y: 0 }}
    >
      {handles}
      {isSyncing && (
        <span
          data-testid="syncing-strip"
          className="pointer-events-none absolute inset-x-2 top-0 z-20 h-0.5 overflow-hidden rounded-full"
        >
          <span className="block h-full w-1/3 animate-[shimmer_1.4s_ease-in-out_infinite] bg-primary/70" />
        </span>
      )}
      <div
        className={surfaceClasses}
        style={surfaceStyle}
        {...(surfaceClipDataAttr != null ? { "data-clip": surfaceClipDataAttr } : {})}
      >
        {hasError && (
          <ValidationBanner
            step={step}
            snapshot={snapshot}
            onOpenDetails={onOpenDetails}
          />
        )}
        <span className="sr-only">{KIND_DOT_LABEL[kind]}</span>
        <HoverActions
          step={step}
          onOpenDetails={onOpenDetails}
          onDuplicate={onDuplicate}
          onDelete={onDelete}
        />
        <div className="relative z-10 flex h-full flex-col gap-1 px-3 py-2">
          {onRename != null ? (
            <InlineRename
              value={name}
              onCommit={handleRenameCommit}
              onCancel={() => {}}
              className={cn(
                "pr-12",
                hasError && "text-destructive",
                isSyncing && "text-primary",
              )}
            />
          ) : (
            <div
              className={cn(
                "truncate pr-12 text-sm font-medium leading-tight",
                hasError ? "text-destructive" : "text-foreground",
              )}
              title={name}
              data-testid="node-title"
            >
              {name}
            </div>
          )}
          {subtitle !== "" && (
            <div
              className="truncate pr-12 text-[11px] leading-tight text-muted-foreground"
              title={subtitle}
              data-testid="node-subtitle"
            >
              {subtitle}
            </div>
          )}
          {reason !== "" && step.rationale != null && (
            <div
              className="truncate pr-12 text-[11px] leading-tight text-muted-foreground"
              title={reasonDetail(step.rationale)}
              data-testid="node-rationale"
            >
              why: {reason}
            </div>
          )}
          {children}
          <div className="mt-auto flex items-center justify-between gap-2">
            <ResultLabel step={step} snapshot={snapshot} />
          </div>
        </div>
      </div>
    </motion.div>
  );
}
