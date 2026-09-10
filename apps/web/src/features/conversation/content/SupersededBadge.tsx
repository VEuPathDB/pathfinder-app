"use client";

import { useAuiState } from "@assistant-ui/react";
import { strategyRevisionPayloadSchema } from "@pathfinder/shared/generated/zod/strategyRevisionPayloadSchema";
import type { ReactElement } from "react";

import type { StructuralPart } from "../parts";

/**
 * Marks an answer whose numbers describe a strategy that has since changed.
 *
 * A turn reports counts that were true when it was written. Editing the
 * strategy afterwards leaves those numbers on screen with nothing saying they
 * are historical - the researcher reads a stale gene count as current fact,
 * which is the failure mode with no error and no zero to notice.
 *
 * The backend already stamps every turn with `data-strategy-revision`
 * (`strategy_revision` hashes inputs only, so a refreshed count never looks
 * like an edit). Nothing consumed it until now.
 */

function isRevisionPart(part: StructuralPart): boolean {
  return (
    part.type === "data-strategy-revision" ||
    (part.type === "data" && part.name === "strategy-revision")
  );
}

type RevisionCarrier = {
  role: string;
  content: readonly StructuralPart[];
};

export function revisionOfMessage(m: RevisionCarrier | undefined): string | null {
  if (m?.role !== "assistant") return null;
  for (let i = m.content.length - 1; i >= 0; i -= 1) {
    const part = m.content[i];
    if (part === undefined || !isRevisionPart(part)) continue;
    const data = strategyRevisionPayloadSchema.safeParse(part.data).data;
    if (data?.revision != null && data.revision !== "") return data.revision;
  }
  return null;
}

type ThreadLike = { messages?: readonly RevisionCarrier[] };

/** The newest revision any turn in the thread reported. */
export function latestRevision(thread: ThreadLike | undefined): string | null {
  const messages = thread?.messages ?? [];
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const revision = revisionOfMessage(messages[i]);
    if (revision !== null) return revision;
  }
  return null;
}

// A primitive ("mine\tlatest") keeps useAuiState's identity check stable;
// returning a fresh object re-renders forever (React #185).
export function SupersededBadge(): ReactElement | null {
  const mine = useAuiState((s) => revisionOfMessage(s.message));
  const latest = useAuiState((s) => latestRevision(s.thread));

  if (mine === null || latest === null || mine === latest) return null;

  return (
    <div
      data-testid="superseded-badge"
      title="The strategy changed after this answer, so any counts here are historical."
      className="inline-flex items-center gap-1.5 self-start py-0.5 text-[11px] text-warning"
    >
      <span className="font-medium">Superseded</span>
      <span aria-hidden>-</span>
      <span>strategy changed since this answer</span>
    </div>
  );
}
