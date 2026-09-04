"use client";

import { AnimatePresence, motion } from "motion/react";
import { GitFork, GitMerge } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  ButtonGroup,
  ButtonGroupSeparator,
  ButtonGroupText,
} from "@/components/ui/button-group";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface SelectionActionBarProps {
  selectedCount: number;
  onCombine: () => void;
  onOrtholog: () => void;
}

const POP_TRANSITION = { type: "spring", stiffness: 500, damping: 24 } as const;

export function SelectionActionBar({
  selectedCount,
  onCombine,
  onOrtholog,
}: SelectionActionBarProps) {
  const visible = selectedCount > 0;
  const canCombine = selectedCount >= 2;
  const canOrtholog = selectedCount === 1;

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          key="selection-action-bar"
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.8, opacity: 0 }}
          transition={POP_TRANSITION}
          data-testid="selection-action-bar"
        >
          <TooltipProvider delayDuration={150}>
            <ButtonGroup
              aria-label="Selection actions"
              className="rounded-md border border-border bg-background shadow-sm"
            >
              <ButtonGroupText className="bg-muted text-xs">
                {selectedCount} selected
              </ButtonGroupText>
              <ButtonGroupSeparator />
              <ActionButton
                label="Combine selected steps (∩)"
                ariaLabel="Combine selected steps"
                disabled={!canCombine}
                onClick={onCombine}
                icon={<GitMerge className="size-4" />}
              />
              <ActionButton
                label="Insert ortholog transform"
                ariaLabel="Insert ortholog transform"
                disabled={!canOrtholog}
                onClick={onOrtholog}
                icon={<GitFork className="size-4" />}
              />
            </ButtonGroup>
          </TooltipProvider>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

interface ActionButtonProps {
  label: string;
  ariaLabel: string;
  disabled: boolean;
  onClick: () => void;
  icon: React.ReactNode;
}

function ActionButton({
  label,
  ariaLabel,
  disabled,
  onClick,
  icon,
}: ActionButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={onClick}
          disabled={disabled}
          aria-label={ariaLabel}
          aria-disabled={disabled}
          className="disabled:opacity-40"
        >
          {icon}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom">{label}</TooltipContent>
    </Tooltip>
  );
}
