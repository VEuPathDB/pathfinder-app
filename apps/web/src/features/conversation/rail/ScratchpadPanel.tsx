"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pin, PinOff, Trash2 } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Note } from "@pathfinder/shared/generated/types/Note";
import { listScratchpadNotesQueryOptions } from "@pathfinder/shared/generated/hooks/useListScratchpadNotes";
import { patchScratchpadNote } from "@pathfinder/shared/generated/hooks/usePatchScratchpadNote";
import { deleteScratchpadNote } from "@pathfinder/shared/generated/hooks/useDeleteScratchpadNote";

import { RailPanelShell } from "./RailPanelShell";

const isPinned = (note: Note): boolean => note.pinned ?? false;

interface ScratchpadPanelProps {
  conversationId: string;
}

export function ScratchpadPanel({ conversationId }: ScratchpadPanelProps) {
  const queryClient = useQueryClient();
  const notesQuery = useQuery(listScratchpadNotesQueryOptions(conversationId));

  const pinMutation = useMutation({
    mutationFn: (args: { noteId: string; pinned: boolean }) =>
      patchScratchpadNote(conversationId, args.noteId, {
        pinned: args.pinned,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: listScratchpadNotesQueryOptions(conversationId).queryKey,
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (noteId: string) => deleteScratchpadNote(conversationId, noteId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: listScratchpadNotesQueryOptions(conversationId).queryKey,
      });
    },
  });

  const notes = notesQuery.data ?? [];
  const pinned = notes.filter((n) => isPinned(n));
  const unpinned = notes.filter((n) => !isPinned(n));

  return (
    <RailPanelShell title="Notes">
      <div data-testid="scratchpad-panel" className="contents">
        {notes.length === 0 && (
          <div
            data-testid="scratchpad-empty"
            className="px-3 py-8 text-center text-sm text-muted-foreground"
          >
            No notes yet. The assistant saves findings here as it works.
          </div>
        )}
        {pinned.length > 0 && (
          <Section label="Pinned">
            {pinned.map((n) => (
              <NoteCard
                key={n.id}
                note={n}
                onTogglePin={() =>
                  pinMutation.mutate({
                    noteId: n.id,
                    pinned: !isPinned(n),
                  })
                }
                onDelete={() => deleteMutation.mutate(n.id)}
              />
            ))}
          </Section>
        )}
        {unpinned.length > 0 && (
          <Section label="Recent">
            {unpinned.map((n) => (
              <NoteCard
                key={n.id}
                note={n}
                onTogglePin={() =>
                  pinMutation.mutate({
                    noteId: n.id,
                    pinned: !isPinned(n),
                  })
                }
                onDelete={() => deleteMutation.mutate(n.id)}
              />
            ))}
          </Section>
        )}
      </div>
    </RailPanelShell>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 px-2 py-1">
      <div className="px-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="flex flex-col gap-1">{children}</div>
    </div>
  );
}

interface NoteCardProps {
  note: Note;
  onTogglePin: () => void;
  onDelete: () => void;
}

function NoteCard({ note, onTogglePin, onDelete }: NoteCardProps) {
  const [expanded, setExpanded] = useState(false);
  const tags = note.tags ?? [];
  const pinned = isPinned(note);
  return (
    <div
      data-testid={`scratchpad-note-${note.id}`}
      data-pinned={pinned ? "true" : "false"}
      className="rounded-md border border-border bg-background p-2 text-sm"
    >
      <div className="flex items-start gap-2">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex-1 text-left"
          aria-expanded={expanded}
        >
          <div className="font-medium">{note.title}</div>
          <div className="text-xs text-muted-foreground">{note.summary}</div>
        </button>
        <div className="flex items-center gap-0.5">
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={onTogglePin}
            aria-label={pinned ? "Unpin" : "Pin"}
            title={pinned ? "Unpin" : "Pin"}
            data-testid={`scratchpad-pin-${note.id}`}
          >
            {pinned ? (
              <PinOff className="h-3.5 w-3.5" />
            ) : (
              <Pin className="h-3.5 w-3.5" />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={onDelete}
            aria-label="Delete note"
            title="Delete"
            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
            data-testid={`scratchpad-delete-${note.id}`}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
      {tags.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1">
          {tags.map((t) => (
            <Badge key={t} variant="secondary" className="text-[10px]">
              {t}
            </Badge>
          ))}
        </div>
      )}
      {expanded && (
        <pre className="mt-2 whitespace-pre-wrap text-xs text-foreground/90">
          {note.body}
        </pre>
      )}
    </div>
  );
}
