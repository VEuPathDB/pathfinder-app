"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";

import type { MemoryEditRequest, MemoryItem } from "@pathfinder/shared";

import {
  deleteMemory,
  editMemory,
  listMemories,
} from "@/features/settings/api/memories";

import { MemoryEditor } from "./memory/MemoryEditor";
import { MemorySearch } from "./memory/MemorySearch";
import { MemorySection } from "./memory/MemorySection";

const PAGE_SIZE = 50;

export function MemorySettings() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<MemoryItem | null>(null);
  const [offset, setOffset] = useState<number>(0);

  const { data, isPending, error, isFetching } = useQuery({
    queryKey: ["memories", "list", offset] as const,
    queryFn: () => listMemories({ limit: PAGE_SIZE, offset }),
    staleTime: 10_000,
    meta: { shownInline: true },
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["memories"] });

  const editMutation = useMutation({
    mutationFn: async (args: {
      key: string;
      kind: MemoryItem["value"]["kind"];
      body: MemoryEditRequest;
    }) => editMemory(args.key, args.kind, args.body),
    onSuccess: () => invalidate(),
  });

  const deleteMutation = useMutation({
    mutationFn: async (args: { key: string; kind: MemoryItem["value"]["kind"] }) =>
      deleteMemory(args.key, args.kind),
    onSuccess: () => invalidate(),
  });

  const handleEditSave = (body: MemoryEditRequest) => {
    if (editing == null) return;
    editMutation.mutate({
      key: editing.key,
      kind: editing.value.kind,
      body,
    });
    setEditing(null);
  };

  const handleDelete = (mem: MemoryItem) => {
    const ok = window.confirm(
      `Delete "${mem.value.name}"? This is recorded as a tombstone so the memory will not re-appear automatically.`,
    );
    if (!ok) return;
    deleteMutation.mutate({ key: mem.key, kind: mem.value.kind });
  };

  const handleToggleAutoRetrieve = (mem: MemoryItem, next: boolean) => {
    editMutation.mutate({
      key: mem.key,
      kind: mem.value.kind,
      body: { autoRetrieve: next },
    });
  };

  return (
    <div className="space-y-4">
      <MemorySearch
        onEdit={(m) => setEditing(m)}
        onDelete={handleDelete}
        onToggleAutoRetrieve={handleToggleAutoRetrieve}
      />

      {isPending && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" />
          Loading memories...
        </div>
      )}

      {error != null && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          Failed to load memories:{" "}
          {error instanceof Error ? error.message : "unknown error"}
        </div>
      )}

      {data != null && (
        <div className="space-y-2">
          <MemorySection
            title="Gene set notes"
            items={data.geneSetNotes}
            onEdit={(m) => setEditing(m)}
            onDelete={handleDelete}
            onToggleAutoRetrieve={handleToggleAutoRetrieve}
          />
          <MemorySection
            title="Strategies"
            items={data.strategies}
            onEdit={(m) => setEditing(m)}
            onDelete={handleDelete}
            onToggleAutoRetrieve={handleToggleAutoRetrieve}
          />
          <MemorySection
            title="Preferences"
            items={data.preferences}
            onEdit={(m) => setEditing(m)}
            onDelete={handleDelete}
            onToggleAutoRetrieve={handleToggleAutoRetrieve}
          />
          <MemorySection
            title="Knowledge"
            items={data.knowledge}
            onEdit={(m) => setEditing(m)}
            onDelete={handleDelete}
            onToggleAutoRetrieve={handleToggleAutoRetrieve}
          />
          <MemorySection
            title="Cases"
            items={data.cases}
            onEdit={(m) => setEditing(m)}
            onDelete={handleDelete}
            onToggleAutoRetrieve={handleToggleAutoRetrieve}
          />

          {(data.hasMore || offset > 0) && (
            <div className="flex items-center justify-between border-t border-border pt-2 text-xs text-muted-foreground">
              <span>
                Showing rows {offset + 1}-{offset + PAGE_SIZE} per namespace
              </span>
              <div className="flex gap-2">
                {offset > 0 && (
                  <button
                    type="button"
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                    disabled={isFetching}
                    className="rounded border border-border px-2 py-1 hover:bg-muted disabled:opacity-50"
                  >
                    Previous
                  </button>
                )}
                {data.hasMore && (
                  <button
                    type="button"
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                    disabled={isFetching}
                    className="rounded border border-border px-2 py-1 hover:bg-muted disabled:opacity-50"
                  >
                    Load more
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      <MemoryEditor
        open={editing != null}
        item={editing}
        onSave={handleEditSave}
        onCancel={() => setEditing(null)}
      />
    </div>
  );
}
