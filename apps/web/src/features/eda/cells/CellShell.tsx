"use client";

import type { ReactNode } from "react";

export interface CellShellProps {
  title: string;
  subtitle: string | null;
  testId: string;
  children: ReactNode;
}

export function CellShell({ title, subtitle, testId, children }: CellShellProps) {
  return (
    <section data-testid={testId} className="flex flex-col gap-2">
      <div className="min-w-0">
        <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {title}
        </h2>
        {subtitle !== null ? (
          <p className="mt-0.5 truncate text-xs text-muted-foreground">{subtitle}</p>
        ) : null}
      </div>
      <div className="rounded-md border border-border bg-card p-3">{children}</div>
    </section>
  );
}
