"use client";

import { useState } from "react";

import type { MemoryEditRequest, MemoryItem } from "@pathfinder/shared";

import { Input } from "@/components/ui/input";

interface MemoryEditorProps {
  open: boolean;
  item: MemoryItem | null;
  onSave: (update: MemoryEditRequest) => void;
  onCancel: () => void;
}

interface EditorDraft {
  name: string;
  summary: string;
  tagsText: string;
  contentText: string;
  autoRetrieve: boolean;
  sourceKey: string;
}

function draftFromItem(item: MemoryItem): EditorDraft {
  return {
    name: item.value.name,
    summary: item.value.summary,
    tagsText: (item.value.tags ?? []).join(", "),
    contentText: JSON.stringify(item.value.content, null, 2),
    autoRetrieve: item.value.autoRetrieve ?? false,
    sourceKey: item.key,
  };
}

function parseContent(
  text: string,
): { ok: true; value: Record<string, unknown> } | { ok: false } {
  try {
    const parsed: unknown = JSON.parse(text);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { ok: false };
    }
    return { ok: true, value: parsed as Record<string, unknown> };
  } catch {
    return { ok: false };
  }
}

function splitTags(text: string): string[] {
  return text
    .split(",")
    .map((t) => t.trim())
    .filter((t) => t.length > 0);
}

export function MemoryEditor({ open, item, onSave, onCancel }: MemoryEditorProps) {
  const [draft, setDraft] = useState<EditorDraft | null>(
    item == null ? null : draftFromItem(item),
  );

  const currentKey = item?.key ?? null;
  if (item != null && draft?.sourceKey !== currentKey) {
    setDraft(draftFromItem(item));
    return null;
  }

  if (!open || item == null || draft == null) return null;

  const parsed = parseContent(draft.contentText);
  const canSave = parsed.ok && draft.name.trim().length > 0;

  const handleSave = () => {
    if (!parsed.ok) return;
    onSave({
      name: draft.name.trim(),
      summary: draft.summary,
      tags: splitTags(draft.tagsText),
      content: parsed.value,
      autoRetrieve: draft.autoRetrieve,
    });
  };

  return (
    <div
      role="dialog"
      aria-label="Edit memory"
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/50 backdrop-blur-sm"
    >
      <div className="w-full max-w-xl rounded-lg border border-border bg-card p-5 shadow-xl">
        <h3 className="mb-3 text-base font-semibold text-foreground">Edit memory</h3>
        <div className="space-y-3">
          <label className="block">
            <span className="text-xs font-medium text-muted-foreground">Name</span>
            <Input
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
          </label>
          <label className="block">
            <span className="text-xs font-medium text-muted-foreground">Summary</span>
            <Input
              value={draft.summary}
              onChange={(e) => setDraft({ ...draft, summary: e.target.value })}
            />
          </label>
          <label className="block">
            <span className="text-xs font-medium text-muted-foreground">
              Tags (comma-separated)
            </span>
            <Input
              value={draft.tagsText}
              onChange={(e) => setDraft({ ...draft, tagsText: e.target.value })}
            />
          </label>
          <label className="block">
            <span className="text-xs font-medium text-muted-foreground">
              Content (JSON)
            </span>
            <textarea
              value={draft.contentText}
              onChange={(e) => setDraft({ ...draft, contentText: e.target.value })}
              rows={6}
              className="mt-1 block w-full rounded-md border border-input bg-transparent px-3 py-2 font-mono text-xs shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-invalid={!parsed.ok}
            />
            {!parsed.ok && (
              <span className="text-xs text-destructive">
                Invalid JSON — must be an object.
              </span>
            )}
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={draft.autoRetrieve}
              onChange={(e) => setDraft({ ...draft, autoRetrieve: e.target.checked })}
              className="h-4 w-4 accent-primary"
            />
            <span className="text-xs font-medium text-muted-foreground">
              Auto-retrieve in future chats
            </span>
          </label>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition hover:bg-muted"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={!canSave}
            className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
