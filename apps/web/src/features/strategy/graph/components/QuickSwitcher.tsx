"use client";

import { useRouter } from "next/navigation";
import type { Step, Strategy } from "@pathfinder/shared";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { strategyStepUrl } from "@/lib/routes";

interface QuickSwitcherProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  strategy: Strategy | null;
}

export function QuickSwitcher({ open, onOpenChange, strategy }: QuickSwitcherProps) {
  const router = useRouter();
  const steps = strategy?.steps ?? [];
  const conversationId = strategy?.id ?? "";

  const handleSelect = (step: Step): void => {
    onOpenChange(false);
    router.push(strategyStepUrl(conversationId, step.id));
  };

  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Jump to step"
      description="Search and select a strategy step to open."
    >
      <CommandInput placeholder="Search steps..." aria-label="Search steps" />
      <CommandList>
        <CommandEmpty>No steps match.</CommandEmpty>
        <CommandGroup heading="Steps">
          {steps.map((step) => (
            <CommandItem
              key={step.id}
              value={`${step.displayName ?? ""} ${step.searchName ?? ""} ${step.id}`}
              onSelect={() => handleSelect(step)}
            >
              <div className="flex flex-col">
                <span className="font-medium">
                  {step.displayName ?? step.searchName ?? step.id}
                </span>
                {step.searchName != null && step.searchName !== "" && (
                  <span className="text-xs text-muted-foreground">
                    {step.searchName}
                  </span>
                )}
              </div>
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
