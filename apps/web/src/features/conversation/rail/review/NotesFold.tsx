"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Note } from "@strategist/shared/generated/types/Note";
import { deleteScratchpadNote } from "@strategist/shared/generated/hooks/useDeleteScratchpadNote";
import { listScratchpadNotesQueryOptions } from "@strategist/shared/generated/hooks/useListScratchpadNotes";
import { patchScratchpadNote } from "@strategist/shared/generated/hooks/usePatchScratchpadNote";
import { Pin, PinOff, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Fold } from "@/lib/components/Fold";
import { useConversationExists } from "@/state/useConversationExists";

import { ReviewSection } from "./ReviewSection";

const isPinned = (note: Note): boolean => note.pinned ?? false;

interface NoteCardProps {
  note: Note;
  onTogglePin: () => void;
  onDelete: () => void;
}

function NoteCard({ note, onTogglePin, onDelete }: NoteCardProps) {
  const [expanded, setExpanded] = useState(false);
  const pinned = isPinned(note);
  return (
    <li
      data-testid={`scratchpad-note-${note.id}`}
      data-pinned={pinned ? "true" : "false"}
      className="rounded-lg border border-border bg-card px-3 py-2 transition-colors duration-120 hover:bg-muted/60"
    >
      <div className="flex items-start gap-2">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="min-w-0 flex-1 text-left"
        >
          <p className="text-sm font-medium text-foreground">{note.title}</p>
          <p className="text-xs text-muted-foreground">{note.summary}</p>
        </button>
        <Button
          variant="ghost"
          size="icon-xs"
          onClick={onTogglePin}
          aria-label={pinned ? "Unpin" : "Pin"}
          data-testid={`scratchpad-pin-${note.id}`}
        >
          {pinned ? <PinOff className="size-3.5" /> : <Pin className="size-3.5" />}
        </Button>
        <Button
          variant="ghost"
          size="icon-xs"
          onClick={onDelete}
          aria-label="Delete note"
          data-testid={`scratchpad-delete-${note.id}`}
          className="text-destructive hover:bg-destructive/10 hover:text-destructive"
        >
          <Trash2 className="size-3.5" />
        </Button>
      </div>
      {expanded && (
        <p
          data-testid="scratchpad-note-body"
          className="mt-2 whitespace-pre-wrap text-xs text-foreground/90"
        >
          {note.body}
        </p>
      )}
    </li>
  );
}

export function NotesFold({ conversationId }: { conversationId: string }) {
  const queryClient = useQueryClient();
  const options = listScratchpadNotesQueryOptions(conversationId);
  const exists = useConversationExists(conversationId);
  const notes = useQuery({ ...options, enabled: exists }).data ?? [];
  const refresh = (): void => {
    void queryClient.invalidateQueries({ queryKey: options.queryKey });
  };
  const pin = useMutation({
    mutationFn: (note: Note) =>
      patchScratchpadNote(conversationId, note.id, { pinned: !isPinned(note) }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (note: Note) => deleteScratchpadNote(conversationId, note.id),
    onSuccess: refresh,
  });
  const ordered = [...notes.filter(isPinned), ...notes.filter((n) => !isPinned(n))];
  return (
    <ReviewSection>
      <Fold
        title="Assistant's notes"
        meta={ordered.length === 0 ? "none" : ordered.length}
      >
        {ordered.length === 0 ? (
          <p data-testid="scratchpad-empty" className="text-xs text-muted-foreground">
            The assistant saves findings here as it works.
          </p>
        ) : (
          <ul data-testid="scratchpad-panel" className="flex flex-col gap-1.5">
            {ordered.map((note) => (
              <NoteCard
                key={note.id}
                note={note}
                onTogglePin={() => pin.mutate(note)}
                onDelete={() => remove.mutate(note)}
              />
            ))}
          </ul>
        )}
      </Fold>
    </ReviewSection>
  );
}
