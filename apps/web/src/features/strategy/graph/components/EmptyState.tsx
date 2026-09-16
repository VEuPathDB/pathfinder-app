"use client";

import { useState } from "react";
import { Plus, Workflow } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AddStepSheet } from "@/features/strategy/graph/components/AddStepSheet";

interface EmptyStateProps {
  siteId: string;
  recordType: string | null;
  conversationId: string;
}

export function EmptyState({ siteId, recordType, conversationId }: EmptyStateProps) {
  const [sheetOpen, setSheetOpen] = useState(false);

  return (
    <div
      className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center"
      data-testid="strategy-empty-state"
    >
      <div className="text-muted-foreground">
        <Workflow className="h-12 w-12" aria-hidden />
      </div>
      <div className="space-y-1">
        <p className="text-sm font-medium text-foreground">Your strategy is empty</p>
        <p className="text-xs text-muted-foreground">
          The agent builds steps as you chat - or add one yourself.
        </p>
      </div>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setSheetOpen(true)}
        className="gap-1.5"
      >
        <Plus className="size-4" aria-hidden />
        Add step
      </Button>
      <AddStepSheet
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        siteId={siteId}
        recordType={recordType}
        conversationId={conversationId}
      />
    </div>
  );
}
