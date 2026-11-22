"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  ClipboardListIcon,
  FileUpIcon,
  FolderIcon,
  ListChecksIcon,
} from "lucide-react";
import type { SaveDatasetMutationRequest } from "@strategist/shared/generated/types/SaveDataset";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SAVE_DATASET_KEY, saveDataset } from "@/lib/api/sites";
import { toUserMessage } from "@/lib/api/errors";
import { cn } from "@/lib/utils/cn";
import { parseGeneCsv } from "@/lib/utils/parseGeneCsv";
import { useSessionStore } from "@/state/useSessionStore";
import type { ParamWidgetProps } from "./types";
import {
  defaultIdListFromInitial,
  parseIdsFromText,
  type DatasetWidgetTab,
} from "./datasetParamLogic";
import {
  BasketTab,
  DefaultTab,
  PasteTab,
  StrategyTab,
  UploadTab,
  type UploadedFile,
} from "./DatasetParamTabs";

const SAVED_DATASET_ID = /^[1-9][0-9]*$/;

export function DatasetParam({
  spec,
  name,
  field,
  disabled = false,
}: ParamWidgetProps) {
  const siteId = useSessionStore((s) => s.selectedSite);
  const raw = typeof field.state.value === "string" ? field.state.value : "";
  const defaultIds = defaultIdListFromInitial(spec.initialDisplayValue);
  const hasDefault = defaultIds.length > 0;

  const [tab, setTab] = useState<DatasetWidgetTab>(() =>
    hasDefault && raw === "" ? "default" : "paste",
  );
  const [pasteText, setPasteText] = useState("");
  const [basketName, setBasketName] = useState("");
  const [strategyId, setStrategyId] = useState("");
  const [upload, setUpload] = useState<UploadedFile | null>(null);

  const [lastSaved, setLastSaved] = useState<string | null>(null);

  const commit = (datasetId: string) => {
    field.handleChange(datasetId);
    field.handleBlur();
  };

  const save = useMutation({
    mutationKey: [...SAVE_DATASET_KEY, siteId],
    mutationFn: (source: SaveDatasetMutationRequest) => saveDataset(siteId, source),
  });

  const saveSource = (source: SaveDatasetMutationRequest) => {
    const key = JSON.stringify(source);
    if (key === lastSaved) return;
    setLastSaved(key);
    save.mutate(source, { onSuccess: commit, onError: () => setLastSaved(null) });
  };

  const saveIds = (ids: string[]) => {
    if (ids.length === 0) return;
    saveSource({ sourceType: "idList", sourceContent: { ids } });
  };

  const applyDefault = () => {
    setPasteText(defaultIds.join("\n"));
    saveIds(defaultIds);
  };

  const handleFileSelected = (file: File, content: string) => {
    const ids = parseGeneCsv(content);
    setUpload({ fileName: file.name, idCount: ids.length });
    setPasteText(ids.join("\n"));
    saveIds(ids);
  };

  const saveBasket = () => {
    const trimmed = basketName.trim();
    if (trimmed === "") return;
    saveSource({ sourceType: "basket", sourceContent: { basketName: trimmed } });
  };

  const pickStrategy = (picked: string) => {
    setStrategyId(picked);
    if (picked === "") return;
    saveSource({
      sourceType: "strategy",
      sourceContent: { strategyId: Number(picked) },
    });
  };

  const hasError = field.state.meta.errors.length > 0;
  const errorMessage = save.isError
    ? toUserMessage(save.error, "The list was not saved on the site")
    : hasError
      ? String(field.state.meta.errors[0])
      : null;

  return (
    <div
      data-testid="dataset-param-root"
      className={cn(
        "rounded-md border bg-card p-3",
        errorMessage !== null
          ? "border-destructive/30 bg-destructive/5"
          : "border-border",
      )}
    >
      <Tabs
        value={tab}
        onValueChange={(value) => setTab(value as DatasetWidgetTab)}
        className="w-full"
      >
        <TabsList className="w-full">
          <TabsTrigger value="paste">
            <ClipboardListIcon className="size-3.5" aria-hidden />
            Paste IDs
          </TabsTrigger>
          {hasDefault && (
            <TabsTrigger value="default">
              <ListChecksIcon className="size-3.5" aria-hidden />
              Default
            </TabsTrigger>
          )}
          <TabsTrigger value="upload">
            <FileUpIcon className="size-3.5" aria-hidden />
            Upload
          </TabsTrigger>
          <TabsTrigger value="basket">
            <FolderIcon className="size-3.5" aria-hidden />
            Basket
          </TabsTrigger>
          <TabsTrigger value="strategy">
            <ListChecksIcon className="size-3.5" aria-hidden />
            Strategy
          </TabsTrigger>
        </TabsList>

        <TabsContent value="paste" className="mt-3">
          <PasteTab
            text={pasteText}
            onTextChange={setPasteText}
            onDone={() => saveIds(parseIdsFromText(pasteText))}
            name={name}
          />
        </TabsContent>
        {hasDefault && (
          <TabsContent value="default" className="mt-3">
            <DefaultTab
              defaultIds={defaultIds}
              isApplied={
                SAVED_DATASET_ID.test(raw) && pasteText === defaultIds.join("\n")
              }
              onApply={applyDefault}
            />
          </TabsContent>
        )}
        <TabsContent value="upload" className="mt-3">
          <UploadTab upload={upload} onFileSelected={handleFileSelected} />
        </TabsContent>
        <TabsContent value="basket" className="mt-3">
          <BasketTab
            value={basketName}
            onChange={setBasketName}
            onDone={saveBasket}
            name={name}
          />
        </TabsContent>
        <TabsContent value="strategy" className="mt-3">
          <StrategyTab value={strategyId} onChange={pickStrategy} disabled={disabled} />
        </TabsContent>
      </Tabs>

      {save.isPending && (
        <p className="mt-2 text-xs text-muted-foreground">
          Saving the list on the site...
        </p>
      )}

      {raw !== "" && (
        <p className="mt-2 text-xs text-warning">
          {SAVED_DATASET_ID.test(raw)
            ? `This step reads saved ID list ${raw} on the site. Paste or upload IDs to replace it.`
            : "This value is not an ID list the editor reads. Paste or upload IDs to replace it."}
        </p>
      )}

      {errorMessage !== null && (
        <p id={`${name}-error`} role="alert" className="mt-2 text-xs text-destructive">
          {errorMessage}
        </p>
      )}
    </div>
  );
}
