"use client";

import { useAuiState } from "@assistant-ui/react";
import { turnRoutePayloadSchema } from "@pathfinder/shared/generated/zod/turnRoutePayloadSchema";
import type { ReactElement } from "react";

import type { StructuralPart } from "../parts";

function isRoutePart(part: StructuralPart): boolean {
  return (
    part.type === "data-turn-route" ||
    (part.type === "data" && part.name === "turn-route")
  );
}

export function exploreRouteOfMessage(
  m: { role: string; content: readonly StructuralPart[] } | undefined,
): boolean {
  if (m?.role !== "assistant") return false;
  return m.content.some(
    (part) =>
      isRoutePart(part) &&
      turnRoutePayloadSchema.safeParse(part.data).data?.route === "explore",
  );
}

export function ExploreMark(): ReactElement | null {
  const explore = useAuiState((s) => exploreRouteOfMessage(s.message));
  if (!explore) return null;
  return (
    <div
      data-testid="explore-mark"
      className="self-start py-0.5 text-[0.6875rem] font-medium text-muted-foreground"
    >
      Explore
    </div>
  );
}
