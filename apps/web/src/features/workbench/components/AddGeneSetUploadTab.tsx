"use client";

import { useRef, useState } from "react";
import { FileUp, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { parseGeneCsv } from "@/lib/utils/parseGeneCsv";
import { cn } from "@/lib/utils/cn";
import { useGeneSetCreation } from "../hooks/useGeneSetCreation";
import { VerificationResults } from "./VerificationResults";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

const ACCEPTED_FILE_TYPES = ".txt,.csv,.tsv";

const stripExtension = (filename: string): string => {
  const dotIndex = filename.lastIndexOf(".");
  return dotIndex > 0 ? filename.slice(0, dotIndex) : filename;
};

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

interface AddGeneSetUploadTabProps {
  onClose: () => void;
  onCreated: () => void;
}

export function AddGeneSetUploadTab({ onClose, onCreated }: AddGeneSetUploadTabProps) {
  const [name, setName] = useState("");
  const [fileText, setFileText] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);

  const {
    error,
    setError,
    isSubmitting,
    verifying,
    resolvedGenes,
    unresolvedIds,
    verified,
    resetVerification,
    handleVerify,
    handleSubmit,
  } = useGeneSetCreation({ onCreated });

  const fileInputRef = useRef<HTMLInputElement>(null);

  const parsedIds = parseGeneCsv(fileText);
  const detectedCount = parsedIds.length;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    resetVerification();
    const reader = new FileReader();
    reader.onload = () => {
      const text = reader.result as string;
      setFileText(text);
      setFileName(file.name);
      if (!name) {
        setName(stripExtension(file.name));
      }
    };
    reader.onerror = () => {
      setError("Failed to read file. Please try again.");
    };
    reader.readAsText(file);
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

      {/* File upload */}
      <div className="mt-4">
        <Label
          htmlFor="gene-ids-upload"
          className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground"
        >
          Upload File
        </Label>
        <div className="mt-1.5">
          <label
            htmlFor="gene-ids-upload"
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed border-border px-4 py-6 transition-colors hover:border-ring hover:bg-muted/50",
              isSubmitting && "pointer-events-none opacity-50",
            )}
          >
            <FileUp className="h-6 w-6 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">
              {fileName ?? "Choose a .txt, .csv, or .tsv file"}
            </span>
            <input
              ref={fileInputRef}
              id="gene-ids-upload"
              type="file"
              accept={ACCEPTED_FILE_TYPES}
              onChange={handleFileChange}
              disabled={isSubmitting}
              className="sr-only"
            />
          </label>
        </div>
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
            void handleSubmit(name, parsedIds, "upload");
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
