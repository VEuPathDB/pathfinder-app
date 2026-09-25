"use client";

import { useQuery } from "@tanstack/react-query";
import type { ModelCatalogEntry } from "@pathfinder/shared";
import { listModelsQueryOptions } from "@pathfinder/shared/generated/hooks/useListModels";

import { readerModel } from "@/lib/models/attachments";
import { useSettingsStore } from "@/state/useSettingsStore";

export interface ReaderModel {
  /** The model that reads the user's message; unknown until the catalog loads. */
  reader: ModelCatalogEntry | undefined;
}

export function useReaderModel(assistantId: string): ReaderModel {
  const { data } = useQuery(listModelsQueryOptions());
  const picks = useSettingsStore((s) => s.phaseModels);
  return {
    reader: readerModel(
      assistantId,
      picks,
      data?.phaseDefaults ?? {},
      data?.models ?? [],
    ),
  };
}
