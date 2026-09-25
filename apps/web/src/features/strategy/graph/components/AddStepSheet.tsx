"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Search, Step } from "@pathfinder/shared";
import { recordTypesOptions, searchesOptions } from "@/lib/api/sites";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Combobox, type ComboboxOption } from "@/components/ui/combobox";
import { useAddStepMutation } from "@/features/strategy/mutations";
import { searchGroupName } from "@/features/strategy/services/searchGroups";

interface AddStepSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  siteId: string;
  /**
   * The strategy's record type. When null, all searches across record types
   * are listed.
   */
  recordType: string | null;
  conversationId: string;
}

const generateStepId = (): string => `step_${Math.random().toString(16).slice(2, 10)}`;

export function AddStepSheet({
  open,
  onOpenChange,
  siteId,
  recordType,
  conversationId,
}: AddStepSheetProps) {
  const addStep = useAddStepMutation(conversationId);
  const { enabled: _enabled, ...searchOpts } = searchesOptions(siteId, recordType);
  const { data: allSearches = [], isPending } = useQuery({
    ...searchOpts,
    enabled: open && siteId !== "",
  });

  const { enabled: _recordTypesEnabled, ...recordTypeOpts } =
    recordTypesOptions(siteId);
  const { data: recordTypes = [] } = useQuery({
    ...recordTypeOpts,
    enabled: open && siteId !== "",
  });

  const [selectedName, setSelectedName] = useState<string | null>(null);

  const groupName = searchGroupName(allSearches, recordTypes);
  const options: ComboboxOption[] = allSearches.map((s) => ({
    value: s.name,
    label: s.displayName !== "" ? s.displayName : s.name,
  }));

  const selected: Search | null =
    allSearches.find((s) => s.name === selectedName) ?? null;

  const handleAdd = (): void => {
    if (selected === null) return;
    const newStep: Step = {
      id: generateStepId(),
      kind: "search",
      displayName: selected.displayName !== "" ? selected.displayName : selected.name,
      searchName: selected.name,
      recordType: selected.recordType,
      parameters: {},
      isFiltered: false,
    };
    addStep.mutate({ step: newStep });
    setSelectedName(null);
    onOpenChange(false);
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="flex w-[440px] flex-col gap-0 p-0 sm:max-w-[440px]"
        data-testid="add-step-sheet"
      >
        <SheetHeader className="border-b border-border">
          <SheetTitle>Add step</SheetTitle>
          <SheetDescription>
            Pick a search to add as a new strategy step.
          </SheetDescription>
        </SheetHeader>
        <div className="flex-1 overflow-auto p-4">
          {isPending ? (
            <div className="text-sm text-muted-foreground">Loading...</div>
          ) : (
            <Combobox
              options={options}
              value={selectedName}
              onChange={setSelectedName}
              placeholder="Pick a search"
              searchPlaceholder="Search..."
              emptyMessage="No matching searches."
              groupBy={(option) => groupName(option.value)}
            />
          )}
          {selected?.description != null && selected.description !== "" && (
            <p className="mt-3 text-xs text-muted-foreground">{selected.description}</p>
          )}
        </div>
        <SheetFooter className="border-t border-border">
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={handleAdd} disabled={selected === null}>
              Add step
            </Button>
          </div>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
