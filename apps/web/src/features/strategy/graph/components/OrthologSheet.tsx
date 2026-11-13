"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Search } from "@strategist/shared";
import { searchesOptions } from "@/lib/api/sites";
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
import { Switch } from "@/components/ui/switch";

interface OrthologSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  siteId: string;
  recordType: string;
  onChoose: (search: Search, options: { insertBetween: boolean }) => void;
}

function looksLikeOrthologSearch(s: Search): boolean {
  const hay = `${s.displayName} ${s.description ?? ""} ${s.name}`.toLowerCase();
  return (
    hay.includes("ortholog") || hay.includes("orthology") || hay.includes("orthomcl")
  );
}

export function OrthologSheet({
  open,
  onOpenChange,
  siteId,
  recordType,
  onChoose,
}: OrthologSheetProps) {
  const { enabled: _enabled, ...searchOpts } = searchesOptions(siteId, recordType);
  const { data: allSearches = [], isPending } = useQuery({
    ...searchOpts,
    enabled: open && siteId !== "",
  });
  const searches = allSearches.filter(looksLikeOrthologSearch);

  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [insertBetween, setInsertBetween] = useState(true);

  const options: ComboboxOption[] = searches.map((s) => ({
    value: s.name,
    label: s.displayName !== "" ? s.displayName : s.name,
  }));

  const selected = searches.find((s) => s.name === selectedName) ?? null;

  const handleConfirm = (): void => {
    if (selected === null) return;
    onChoose(selected, { insertBetween });
    onOpenChange(false);
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="flex w-[440px] flex-col gap-0 p-0 sm:max-w-[440px]"
        data-testid="ortholog-sheet"
      >
        <SheetHeader className="border-b border-border">
          <SheetTitle>Insert ortholog transform</SheetTitle>
          <SheetDescription>
            Pick the site&apos;s ortholog/orthology transform. You can edit parameters
            after insertion.
          </SheetDescription>
        </SheetHeader>
        <div className="flex-1 overflow-auto p-4">
          <div className="space-y-4">
            <div className="space-y-2">
              <label
                htmlFor="ortholog-search-picker"
                className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
              >
                Transform tool
              </label>
              {isPending ? (
                <div className="text-sm text-muted-foreground">Loading...</div>
              ) : searches.length === 0 ? (
                <div className="text-sm text-muted-foreground">
                  No ortholog transforms found for this record type.
                </div>
              ) : (
                <Combobox
                  options={options}
                  value={selectedName}
                  onChange={setSelectedName}
                  placeholder="Pick a transform"
                  searchPlaceholder="Search transforms..."
                  emptyMessage="No matching transforms."
                />
              )}
              {selected?.description != null && selected.description !== "" && (
                <p className="text-xs text-muted-foreground">{selected.description}</p>
              )}
            </div>
            <div className="flex items-start justify-between gap-3 rounded-md border border-border bg-card p-3">
              <div className="space-y-0.5">
                <label
                  htmlFor="ortholog-insert-between"
                  className="text-sm font-medium text-foreground"
                >
                  Insert between
                </label>
                <p className="text-xs text-muted-foreground">
                  When the selected step has a downstream step, insert the transform
                  between them and rewire the chain.
                </p>
              </div>
              <Switch
                id="ortholog-insert-between"
                checked={insertBetween}
                onCheckedChange={setInsertBetween}
              />
            </div>
          </div>
        </div>
        <SheetFooter className="border-t border-border">
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={handleConfirm} disabled={selected === null}>
              Insert
            </Button>
          </div>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
