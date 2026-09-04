"use client";

import { useState } from "react";
import { Check } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import type { ModelCatalogEntry, ModelProvider } from "@pathfinder/shared";
import { listModelsQueryOptions } from "@pathfinder/shared/generated/hooks/useListModels";
import { Modal } from "@/lib/components/Modal";
import { ProviderIcon } from "@/lib/components/ProviderIcon";
import { formatCompactClean, formatPrice } from "@/features/settings/format";
import { PROVIDER_TABS } from "@/lib/models/providerMeta";

type SortKey =
  | "name"
  | "contextSize"
  | "inputPrice"
  | "outputPrice"
  | "cachedInputPrice";
type SortDir = "asc" | "desc";

interface ModelCatalogModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelect?: (modelId: string) => void;
}

function compareModels(
  a: ModelCatalogEntry,
  b: ModelCatalogEntry,
  key: SortKey,
  dir: SortDir,
): number {
  const valA = a[key];
  const valB = b[key];
  if (typeof valA === "string" && typeof valB === "string") {
    return dir === "asc" ? valA.localeCompare(valB) : valB.localeCompare(valA);
  }
  const numA = typeof valA === "number" ? valA : 0;
  const numB = typeof valB === "number" ? valB : 0;
  return dir === "asc" ? numA - numB : numB - numA;
}

export function ModelCatalogModal({
  open,
  onOpenChange,
  onSelect,
}: ModelCatalogModalProps) {
  const { data } = useQuery(listModelsQueryOptions());
  const catalog = data?.models ?? [];
  const [providerFilter, setProviderFilter] = useState<"all" | ModelProvider>("all");
  const [sortKey, setSortKey] = useState<SortKey>("inputPrice");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const presentProviders = new Set(catalog.map((m) => m.provider));
  const availableProviders = PROVIDER_TABS.filter(
    (t) => t.key === "all" || presentProviders.has(t.key),
  );

  const filteredBase =
    providerFilter === "all"
      ? catalog
      : catalog.filter((m) => m.provider === providerFilter);
  const filtered = [...filteredBase].sort((a, b) =>
    compareModels(a, b, sortKey, sortDir),
  );

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  function sortIndicator(key: SortKey): string {
    if (sortKey !== key) return "";
    return sortDir === "asc" ? " ▴" : " ▾";
  }

  return (
    <Modal
      open={open}
      onClose={() => onOpenChange(false)}
      title="Model Catalog"
      maxWidth="max-w-4xl"
      showCloseButton
    >
      <div className="flex flex-col max-h-[80vh]">
        <div className="px-5 pt-5 pb-3">
          <p className="text-xs text-muted-foreground mt-0.5">
            Compare models by pricing, context size, and capabilities.
          </p>
        </div>

        <div className="px-5 pb-3 flex gap-1">
          {availableProviders.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setProviderFilter(tab.key)}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                providerFilter === tab.key
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted/50 text-muted-foreground hover:bg-muted"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-auto px-5 pb-2">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border/50 text-left text-muted-foreground">
                <th className="pb-2 pr-3 font-medium">
                  <button
                    type="button"
                    onClick={() => toggleSort("name")}
                    className="hover:text-foreground transition-colors"
                  >
                    Model{sortIndicator("name")}
                  </button>
                </th>
                <th className="pb-2 px-3 font-medium text-right">
                  <button
                    type="button"
                    onClick={() => toggleSort("contextSize")}
                    className="hover:text-foreground transition-colors"
                  >
                    Context{sortIndicator("contextSize")}
                  </button>
                </th>
                <th className="pb-2 px-3 font-medium text-right">
                  <button
                    type="button"
                    onClick={() => toggleSort("inputPrice")}
                    className="hover:text-foreground transition-colors"
                  >
                    Input $/MTok{sortIndicator("inputPrice")}
                  </button>
                </th>
                <th className="pb-2 px-3 font-medium text-right">
                  <button
                    type="button"
                    onClick={() => toggleSort("outputPrice")}
                    className="hover:text-foreground transition-colors"
                  >
                    Output $/MTok{sortIndicator("outputPrice")}
                  </button>
                </th>
                <th className="pb-2 px-3 font-medium text-right">
                  <button
                    type="button"
                    onClick={() => toggleSort("cachedInputPrice")}
                    className="hover:text-foreground transition-colors"
                  >
                    Cached $/MTok{sortIndicator("cachedInputPrice")}
                  </button>
                </th>
                <th className="pb-2 px-3 font-medium">Best For</th>
                {onSelect && <th className="pb-2 pl-3 font-medium w-16" />}
              </tr>
            </thead>
            <tbody>
              {filtered.map((model) => (
                <ModelRow
                  key={model.id}
                  model={model}
                  {...(onSelect != null ? { onSelect } : {})}
                  onClose={() => onOpenChange(false)}
                />
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td
                    colSpan={onSelect ? 7 : 6}
                    className="py-8 text-center text-muted-foreground"
                  >
                    No models found for this provider.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="px-5 py-3 border-t border-border/40 text-[10px] text-muted-foreground">
          Prices per 1M tokens (USD)
        </div>
      </div>
    </Modal>
  );
}

function ModelRow({
  model,
  onSelect,
  onClose,
}: {
  model: ModelCatalogEntry;
  onSelect?: (modelId: string) => void;
  onClose: () => void;
}) {
  const isEnabled = model.enabled ?? true;
  const supportsReasoning = model.supportsReasoning ?? false;
  const description =
    model.description != null && model.description !== "" ? model.description : "—";

  function handleSelect() {
    if (onSelect == null || !isEnabled) return;
    onSelect(model.id);
    onClose();
  }

  return (
    <tr
      className={`border-b border-border/20 ${
        isEnabled ? "hover:bg-muted/30 transition-colors" : "opacity-50"
      }`}
    >
      <td className="py-2.5 pr-3">
        <div className="flex items-center gap-2">
          <ProviderIcon provider={model.provider} size={14} />
          <div>
            <div className="font-medium text-foreground">{model.name}</div>
            {supportsReasoning && (
              <span className="text-[10px] text-primary/80">reasoning</span>
            )}
          </div>
        </div>
      </td>
      <td className="py-2.5 px-3 text-right text-muted-foreground">
        {formatCompactClean(model.contextSize ?? 0)}
      </td>
      <td className="py-2.5 px-3 text-right text-success">
        {formatPrice(model.inputPrice ?? 0)}
      </td>
      <td className="py-2.5 px-3 text-right text-warning">
        {formatPrice(model.outputPrice ?? 0)}
      </td>
      <td className="py-2.5 px-3 text-right text-primary/80">
        {formatPrice(model.cachedInputPrice ?? 0)}
      </td>
      <td className="py-2.5 px-3 text-muted-foreground max-w-[160px] truncate">
        {description}
      </td>
      {onSelect && (
        <td className="py-2.5 pl-3">
          <button
            type="button"
            disabled={!isEnabled}
            onClick={handleSelect}
            className="inline-flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium transition-colors bg-primary/10 text-primary hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Check className="h-3 w-3" />
            Select
          </button>
        </td>
      )}
    </tr>
  );
}
