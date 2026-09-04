"use client";

import { useState } from "react";
import { Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { parseGeneIds } from "@/features/workbench/utils/parseGeneIds";
import { useGeneSetCreation } from "../hooks/useGeneSetCreation";
import { VerificationResults } from "./VerificationResults";

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

interface AddGeneSetPasteTabProps {
  onClose: () => void;
  onCreated: () => void;
}

export function AddGeneSetPasteTab({ onClose, onCreated }: AddGeneSetPasteTabProps) {
  const [name, setName] = useState("");
  const [pasteText, setPasteText] = useState("");

  const {
    error,
    isSubmitting,
    verifying,
    resolvedGenes,
    unresolvedIds,
    verified,
    resetVerification,
    handleVerify,
    handleSubmit,
  } = useGeneSetCreation({ onCreated });

  const parsedIds = parseGeneIds(pasteText);
  const detectedCount = parsedIds.length;

  const handlePasteChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setPasteText(e.target.value);
    resetVerification();
  };

  return (
    <>
      {/* Name input */}
      <div>
        <Label
          htmlFor="gene-set-name"
          className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground"
        >
          Name
        </Label>
        <Input
          id="gene-set-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. My upregulated genes"
          disabled={isSubmitting}
          className="mt-1.5 bg-background"
        />
      </div>

      {/* Textarea */}
      <div className="mt-4">
        <Label
          htmlFor="gene-ids-paste"
          className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground"
        >
          Gene IDs
        </Label>
        <textarea
          id="gene-ids-paste"
          value={pasteText}
          onChange={handlePasteChange}
          placeholder="Paste gene IDs separated by newlines, commas, or tabs"
          rows={5}
          disabled={isSubmitting}
          className="mt-1.5 w-full resize-none rounded-md border border-border bg-background px-3 py-2 font-mono text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
        />
      </div>

      {/* Detection + verify row */}
      {detectedCount > 0 && (
        <div className="mt-3 flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            {detectedCount} gene{detectedCount !== 1 ? "s" : ""} detected
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              void handleVerify(parsedIds);
            }}
            loading={verifying}
            disabled={verifying || isSubmitting}
            className="gap-1 text-xs"
          >
            <Search className="h-3 w-3" />
            Verify IDs
          </Button>
        </div>
      )}

      {/* Verification results */}
      {verified && resolvedGenes !== null && (
        <VerificationResults
          resolvedGenes={resolvedGenes}
          unresolvedIds={unresolvedIds}
        />
      )}

      {/* Error */}
      {error != null && error !== "" && (
        <p className="mt-3 text-xs text-destructive" role="alert">
          {error}
        </p>
      )}

      {/* Actions */}
      <div className="mt-5 flex justify-end gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onClose}
          disabled={isSubmitting}
        >
          Cancel
        </Button>
        <Button
          type="button"
          size="sm"
          onClick={() => {
            void handleSubmit(name, parsedIds, "paste");
          }}
          loading={isSubmitting}
          disabled={detectedCount === 0}
        >
          {verified && resolvedGenes
            ? `Add ${resolvedGenes.length} Gene${resolvedGenes.length !== 1 ? "s" : ""}`
            : "Add Gene Set"}
        </Button>
      </div>
    </>
  );
}
