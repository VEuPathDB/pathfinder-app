"use client";

import { useQuery } from "@tanstack/react-query";
import { useDebounce } from "use-debounce";
import type { ResolvedGene } from "@pathfinder/shared";
import { resolveGenes } from "@pathfinder/shared/generated/hooks/useResolveGenes";
import { GeneChip, type ChipStatus } from "./GeneChip";
import { GeneAutocomplete } from "./GeneAutocomplete";
import { GeneSetPicker } from "./GeneSetPicker";
import { CsvImportButton } from "./CsvImportButton";
import { Label } from "@/components/ui/label";

interface GeneChipInputProps {
  siteId: string;
  value: string[];
  onChange: (ids: string[]) => void;
  label: string;
  required?: boolean;
  tint?: "positive" | "negative" | "neutral";
}

export function GeneChipInput({
  siteId,
  value,
  onChange,
  label,
  required = false,
  tint = "neutral",
}: GeneChipInputProps) {
  const [debouncedValue] = useDebounce(value, 500);

  const sortedKey = [...debouncedValue].sort().join(",");

  const { data: verification } = useQuery({
    queryKey: ["gene-verify", siteId, sortedKey] as const,
    queryFn: async () => {
      const result = await resolveGenes(siteId, { geneIds: debouncedValue });
      const resolved = new Map<string, ResolvedGene>();
      const invalid = new Set<string>();
      for (const gene of result.resolved) resolved.set(gene.geneId, gene);
      for (const id of result.unresolved) invalid.add(id);
      return { resolved, invalid };
    },
    enabled: debouncedValue.length > 0 && siteId !== "",
    staleTime: 60_000,
    retry: false,
  });

  const resolved = verification?.resolved ?? new Map<string, ResolvedGene>();
  const invalid = verification?.invalid ?? new Set<string>();

  const getChipStatus = (geneId: string): ChipStatus => {
    if (resolved.has(geneId)) return "verified";
    if (invalid.has(geneId)) return "invalid";
    return "pending";
  };

  const handleRemove = (geneId: string) => {
    onChange(value.filter((id) => id !== geneId));
  };

  const handleAdd = (geneId: string) => {
    if (!value.includes(geneId)) onChange([...value, geneId]);
  };

  const handleBulkAdd = (ids: string[]) => {
    const unique = ids.filter((id) => !value.includes(id));
    if (unique.length > 0) onChange([...value, ...unique]);
  };

  const tintBorder =
    tint === "positive"
      ? "border-l-success"
      : tint === "negative"
        ? "border-l-warning"
        : "border-l-muted";

  return (
    <div
      data-testid="gene-chip-input"
      data-tint={tint}
      className={`space-y-1.5 border-l-2 pl-2.5 ${tintBorder}`}
    >
      <Label className="text-xs font-medium">
        {label}
        {required && <span className="ml-0.5 text-destructive">*</span>}
      </Label>

      <div className="flex flex-wrap gap-1">
        {value.map((geneId) => (
          <GeneChip
            key={geneId}
            geneId={geneId}
            status={getChipStatus(geneId)}
            resolvedGene={resolved.get(geneId) ?? null}
            onRemove={() => handleRemove(geneId)}
          />
        ))}
      </div>

      <div className="flex items-center gap-1.5">
        <GeneAutocomplete
          siteId={siteId}
          onSelect={handleAdd}
          excludeIds={new Set(value)}
        />
        <GeneSetPicker onSelect={handleBulkAdd} />
        <CsvImportButton onImport={handleBulkAdd} />
      </div>
    </div>
  );
}
