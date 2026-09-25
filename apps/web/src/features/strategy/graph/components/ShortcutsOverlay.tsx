"use client";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface ShortcutsOverlayProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface ShortcutEntry {
  keys: string;
  label: string;
}

interface ShortcutColumn {
  heading: string;
  entries: ShortcutEntry[];
}

const COLUMNS: ShortcutColumn[] = [
  {
    heading: "Canvas",
    entries: [
      { keys: "R", label: "Tidy layout" },
      { keys: "F", label: "Fit to view" },
      { keys: "+", label: "Zoom in" },
      { keys: "−", label: "Zoom out" },
      { keys: "?", label: "Show shortcuts" },
    ],
  },
  {
    heading: "Selection",
    entries: [
      { keys: "E", label: "Edit selected step" },
      { keys: "C", label: "Combine selected (≥2)" },
      { keys: "O", label: "Insert ortholog (1)" },
      { keys: "Del", label: "Delete selected" },
      { keys: "⌘A", label: "Select all" },
      { keys: "⌘Z", label: "Undo" },
      { keys: "⌘⇧Z", label: "Redo" },
    ],
  },
  {
    heading: "Navigation",
    entries: [
      { keys: "⌘K", label: "Quick switcher" },
      { keys: "G then S", label: "Go to strategy" },
      { keys: "G then C", label: "Go to conversation" },
      { keys: "Esc", label: "Close sheet / back" },
    ],
  },
];

export function ShortcutsOverlay({ open, onOpenChange }: ShortcutsOverlayProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription>
            Press <Kbd>?</Kbd> any time to toggle this list.
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
          {COLUMNS.map((col) => (
            <section key={col.heading} className="flex flex-col gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {col.heading}
              </h3>
              <ul className="flex flex-col gap-1.5">
                {col.entries.map((entry) => (
                  <li
                    key={`${col.heading}-${entry.keys}`}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <span className="text-foreground">{entry.label}</span>
                    <Kbd>{entry.keys}</Kbd>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex min-w-[1.5rem] items-center justify-center rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
      {children}
    </kbd>
  );
}
