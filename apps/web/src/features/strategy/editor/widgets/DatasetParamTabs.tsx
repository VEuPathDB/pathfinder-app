"use client";

import { FileUpIcon } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Combobox, type ComboboxOption } from "@/components/ui/combobox";
import { listStrategiesQueryOptions } from "@pathfinder/shared/generated/hooks/useListStrategies";
import { useSessionStore } from "@/state/useSessionStore";
import { parseIdsFromText } from "./datasetParamLogic";

interface PasteTabProps {
  text: string;
  onTextChange: (text: string) => void;
  name: string;
}

export function PasteTab({ text, onTextChange, name }: PasteTabProps) {
  const ids = parseIdsFromText(text);
  return (
    <div className="space-y-2">
      <Textarea
        id={`${name}-paste`}
        aria-label="Paste IDs"
        value={text}
        onChange={(event) => onTextChange(event.target.value)}
        placeholder="One ID per line, or comma-separated.&#10;PF3D7_0100100&#10;PF3D7_0200200"
        rows={6}
        className="font-mono text-xs"
      />
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Badge variant="outline" className="px-1.5 py-0 text-[10px]">
          {ids.length === 1 ? "1 ID" : `${String(ids.length)} IDs`}
        </Badge>
        <span>Source: idList</span>
      </div>
    </div>
  );
}

interface DefaultTabProps {
  defaultIds: string[];
  isApplied: boolean;
  onApply: () => void;
}

export function DefaultTab({ defaultIds, isApplied, onApply }: DefaultTabProps) {
  return (
    <div className="space-y-2">
      <div className="rounded-md border border-border bg-muted/30 p-2 font-mono text-xs">
        {defaultIds.length === 0
          ? "(default list is empty)"
          : defaultIds.slice(0, 12).join(", ") +
            (defaultIds.length > 12 ? ` ...+${String(defaultIds.length - 12)}` : "")}
      </div>
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">
          {defaultIds.length === 1
            ? "1 default ID"
            : `${String(defaultIds.length)} default IDs`}
        </span>
        <Button type="button" size="sm" onClick={onApply} disabled={isApplied}>
          {isApplied ? "Using default" : "Use this"}
        </Button>
      </div>
    </div>
  );
}

interface UploadTabProps {
  fileName: string;
  onFileSelected: (file: File, content: string) => void;
}

export function UploadTab({ fileName, onFileSelected }: UploadTabProps) {
  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const content =
        typeof reader.result === "string"
          ? reader.result
          : new TextDecoder().decode(reader.result ?? new ArrayBuffer(0));
      onFileSelected(file, content);
    };
    reader.readAsText(file);
  };
  return (
    <div className="space-y-2">
      <label
        htmlFor="dataset-file-input"
        className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground hover:bg-muted/50"
      >
        <FileUpIcon className="size-4" aria-hidden />
        <span>{fileName !== "" ? `Replace (${fileName})` : "Choose file"}</span>
      </label>
      <input
        id="dataset-file-input"
        type="file"
        accept=".txt,.csv,.tsv,.list"
        aria-label="Upload file"
        className="sr-only"
        onChange={handleChange}
      />
      {fileName !== "" && (
        <div className="text-xs text-muted-foreground">
          Selected file: <span className="font-mono">{fileName}</span>
        </div>
      )}
      <p className="text-[11px] text-muted-foreground">
        Plain text file: one ID per line, or comma-separated.
      </p>
    </div>
  );
}

interface BasketTabProps {
  value: string;
  onChange: (value: string) => void;
  name: string;
}

export function BasketTab({ value, onChange, name }: BasketTabProps) {
  return (
    <div className="space-y-2">
      <label
        htmlFor={`${name}-basket-name`}
        className="block text-xs text-muted-foreground"
      >
        Basket name
      </label>
      <Input
        id={`${name}-basket-name`}
        aria-label="Basket name"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="e.g. Genes"
      />
      <p className="text-xs text-muted-foreground">Source: basket</p>
    </div>
  );
}

interface StrategyTabProps {
  value: string;
  onChange: (value: string) => void;
}

export function StrategyTab({ value, onChange }: StrategyTabProps) {
  const siteId = useSessionStore((s) => s.selectedSite);
  const { data, isPending, isError } = useQuery({
    ...listStrategiesQueryOptions({ siteId }),
    enabled: siteId !== "",
    meta: { shownInline: true },
  });

  const options: ComboboxOption[] = (data ?? []).map((conv) => ({
    value: conv.id,
    label: conv.name === "" ? `Untitled (${conv.id.slice(0, 8)})` : conv.name,
  }));

  return (
    <div className="space-y-2">
      <label className="block text-xs text-muted-foreground">Pick a strategy</label>
      {isError && (
        <p className="text-xs text-destructive">
          Couldn&apos;t load strategies for this site.
        </p>
      )}
      <Combobox
        options={options}
        value={value === "" ? null : value}
        onChange={(next) => onChange(next ?? "")}
        placeholder={isPending ? "Loading..." : "Select a strategy..."}
        emptyMessage="No strategies available for this site."
        searchPlaceholder="Search strategies..."
      />
      <p className="text-[11px] text-muted-foreground">Source: strategy</p>
    </div>
  );
}
