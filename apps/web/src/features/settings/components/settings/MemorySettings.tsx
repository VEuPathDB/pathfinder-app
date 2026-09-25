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
import { toUserMessage } from "@/lib/api/errors";
import { MEMORY_KIND_LABELS, memorySections } from "@/lib/memoryKinds";
import { useMemoryFocusStore } from "@/state/useMemoryFocusStore";

import { MemoryEditor } from "./memory/MemoryEditor";
import { MemorySearch } from "./memory/MemorySearch";
import { MemorySection } from "./memory/MemorySection";

const PAGE_SIZE = 50;

export function MemorySettings() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<MemoryItem | null>(null);
  const [offset, setOffset] = useState<number>(0);
  const focused = useMemoryFocusStore((s) => s.focused);

  const { data, isPending, error, isFetching } = useQuery({
    queryKey: ["memories", "list", offset] as const,
    queryFn: () => listMemories({ limit: PAGE_SIZE, offset }),
    staleTime: 10_000,
    meta: { shownInline: true },
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["memories"] });

  const [failure, setFailure] = useState<string | null>(null);

  const editMutation = useMutation({
    mutationFn: async (args: {
      item: MemoryItem;
      body: MemoryEditRequest;
      action: "save" | "change auto-retrieve for";
    }) => editMemory(args.item.key, args.item.value.kind, args.body),
    onMutate: () => setFailure(null),
    onSuccess: () => invalidate(),
    onError: (err, { item, action }) => {
      setFailure(`Could not ${action} "${item.value.name}": ${toUserMessage(err)}`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (item: MemoryItem) => deleteMemory(item.key, item.value.kind),
    onMutate: () => setFailure(null),
    onSuccess: () => invalidate(),
    onError: (err, item) => {
      setFailure(`Could not delete "${item.value.name}": ${toUserMessage(err)}`);
    },
  });

  const handleEditSave = (body: MemoryEditRequest) => {
    if (editing == null) return;
    editMutation.mutate(
      { item: editing, body, action: "save" },
      { onSuccess: () => setEditing(null) },
    );
  };

  const handleDelete = (mem: MemoryItem) => {
    const ok = window.confirm(
      `Delete "${mem.value.name}"? PathFinder will not save it again on its own.`,
    );
    if (!ok) return;
    deleteMutation.mutate(mem);
  };

  const handleToggleAutoRetrieve = (mem: MemoryItem, next: boolean) => {
    editMutation.mutate({
      item: mem,
      body: { autoRetrieve: next },
      action: "change auto-retrieve for",
    });
  };

  return (
    <div className="space-y-4">
      <MemorySearch
        onEdit={(m) => setEditing(m)}
        onDelete={handleDelete}
        onToggleAutoRetrieve={handleToggleAutoRetrieve}
      />

      {failure != null && (
        <div
          role="alert"
          className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
        >
          {failure}
        </div>
      )}

      {isPending && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" />
          Loading memories...
        </div>
      )}

      {error != null && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          Failed to load memories: {toUserMessage(error)}
        </div>
      )}

      {data != null && (
        <div className="space-y-2">
          {memorySections(data).map(({ kind, items }) => (
            <MemorySection
              key={kind}
              title={MEMORY_KIND_LABELS[kind].many}
              items={items}
              focusedKey={focused?.kind === kind ? focused.key : null}
              defaultOpen={focused?.kind === kind}
              onEdit={(m) => setEditing(m)}
              onDelete={handleDelete}
              onToggleAutoRetrieve={handleToggleAutoRetrieve}
            />
          ))}

          {(data.hasMore || offset > 0) && (
            <div className="flex items-center justify-between border-t border-border pt-2 text-xs text-muted-foreground">
              <span>
                Showing memories {offset + 1}-{offset + PAGE_SIZE} of each kind
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
