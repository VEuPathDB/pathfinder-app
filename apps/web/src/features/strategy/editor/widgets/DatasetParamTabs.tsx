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
        <span>The site saves these IDs as a new list.</span>
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
        {defaultIds.slice(0, 12).join(", ") +
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

export interface UploadedFile {
  fileName: string;
  idCount: number;
}

interface UploadTabProps {
  upload: UploadedFile | null;
  onFileSelected: (file: File, content: string) => void;
}

export function UploadTab({ upload, onFileSelected }: UploadTabProps) {
  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    void file.text().then((content) => onFileSelected(file, content));
  };
  return (
    <div className="space-y-2">
      <label
        htmlFor="dataset-file-input"
        className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground hover:bg-muted/50"
      >
        <FileUpIcon className="size-4" aria-hidden />
        <span>{upload !== null ? "Replace file" : "Choose file"}</span>
      </label>
      <input
        id="dataset-file-input"
        type="file"
        accept=".txt,.csv,.tsv,.list"
        aria-label="Upload file"
        className="sr-only"
        onChange={handleChange}
      />
      {upload !== null && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="font-mono">{upload.fileName}</span>
          <Badge variant="outline" className="px-1.5 py-0 text-[10px]">
            {upload.idCount === 1 ? "1 ID" : `${String(upload.idCount)} IDs`}
          </Badge>
        </div>
      )}
      <p className="text-[11px] text-muted-foreground">
        Plain text or CSV file: one ID per line, the ID in the first column.
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
        Basket record type
      </label>
      <Input
        id={`${name}-basket-name`}
        aria-label="Basket record type"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="transcript"
      />
      <p className="text-xs text-muted-foreground">
        The site reads the records in your basket of this type; genes are transcript.
      </p>
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

  const options: ComboboxOption[] = (data ?? []).flatMap((conv) =>
    conv.wdkStrategyId == null
      ? []
      : [
          {
            value: String(conv.wdkStrategyId),
            label: conv.name === "" ? `Untitled (${conv.id.slice(0, 8)})` : conv.name,
          },
        ],
  );

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
        emptyMessage="No strategy on this site is built yet."
        searchPlaceholder="Search strategies..."
      />
      <p className="text-[11px] text-muted-foreground">
        The site reads the IDs this strategy answers.
      </p>
    </div>
  );
}
