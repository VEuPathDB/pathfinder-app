"use client";

import { useAuiState } from "@assistant-ui/react";
import { runningPhase } from "@veupathdb/assistant-client";
import type { TurnStatusPayload } from "@pathfinder/shared/generated/types/TurnStatusPayload";
import { turnStatusPayloadSchema } from "@pathfinder/shared/generated/zod/turnStatusPayloadSchema";
import { useState } from "react";

import { Shimmer } from "@/components/ai-elements/shimmer";
import { ProviderIcon } from "@/lib/components/ProviderIcon";
import { phaseLabel } from "@/lib/models/phaseRoles";
import { isLocalProvider, parseModelString } from "@/lib/models/providerMeta";

import { protocolPart, type StructuralPart } from "../parts";
import { currentSeconds, statusLineWith, useNowSeconds } from "./statusClock";

const DEFAULT_LABEL = "Thinking...";
const SUB_AGENT_CALL = "data-sub-agent-call";

interface StatusCarrier {
  status?: { type: string } | undefined;
  content: readonly StructuralPart[];
}

function turnStatusData(part: StructuralPart): TurnStatusPayload | null {
  const isTurnStatus =
    part.type === "data-turn-status" ||
    (part.type === "data" &&
      (part.name === "turn-status" || part.name === "data-turn-status"));
  if (!isTurnStatus) return null;
  return turnStatusPayloadSchema.safeParse(part.data).data ?? null;
}

// Selectors return primitives so useAuiState's identity check doesn't loop
// (React #185). An open dispatch names the phase unless a status the turn
// wrote after it, with no model waited on, is the latest one standing; an
// empty label withdraws the label before it.
export function selectStatusLabel(m: StatusCarrier | undefined): string | null {
  if (m == null || m.status?.type !== "running") return null;
  const parts = m.content.map(protocolPart);
  const said: { label: string; waitingOnLlm: boolean; at: number }[] = [];
  let dispatchedAt = -1;
  m.content.forEach((part, at) => {
    if (parts[at]?.type === SUB_AGENT_CALL) dispatchedAt = at;
    const data = turnStatusData(part);
    if (data === null) return;
    if (data.label.length === 0) said.pop();
    else said.push({ label: data.label, waitingOnLlm: data.waitingOnLlm ?? false, at });
  });
  const standing = said.at(-1);
  const phase = runningPhase(parts);
  if (phase === null) return standing?.label ?? DEFAULT_LABEL;
  if (standing !== undefined && !standing.waitingOnLlm && standing.at > dispatchedAt) {
    return standing.label;
  }
  return `${phaseLabel(phase)}...`;
}

function selectStatusModel(m: StatusCarrier | undefined): string | null {
  if (m == null || m.status?.type !== "running") return null;
  let model: string | null = null;
  for (const part of m.content) {
    const data = turnStatusData(part);
    if (data?.model != null && data.model.length > 0) {
      model = data.model;
    }
  }
  return model;
}

export function selectPartsFingerprint(m: StatusCarrier | undefined): string {
  if (m == null) return "";
  const last = m.content.at(-1);
  const growth =
    last != null && "text" in last && typeof last.text === "string"
      ? last.text.length
      : 0;
  return `${m.content.length}:${last?.type ?? ""}:${growth}`;
}

export function AssistantThinkingPlaceholder() {
  const label = useAuiState((s) => selectStatusLabel(s.message));
  const model = useAuiState((s) => selectStatusModel(s.message));
  const fingerprint = useAuiState((s) => selectPartsFingerprint(s.message));
  const now = useNowSeconds();
  const [seenFingerprint, setSeenFingerprint] = useState(fingerprint);
  const [changedAt, setChangedAt] = useState(currentSeconds);
  if (fingerprint !== seenFingerprint) {
    setSeenFingerprint(fingerprint);
    setChangedAt(currentSeconds());
  }
  if (typeof label !== "string") return null;
  const provider = model !== null ? parseModelString(model).provider : null;
  return (
    <div data-testid="assistant-status" className="flex items-center gap-2 py-0.5">
      {provider !== null && !isLocalProvider(provider) && (
        <ProviderIcon
          provider={provider}
          size={14}
          className="shrink-0 text-muted-foreground"
        />
      )}
      <Shimmer as="span" className="text-sm font-medium" duration={1.2}>
        {statusLineWith(label, now - changedAt)}
      </Shimmer>
    </div>
  );
}
