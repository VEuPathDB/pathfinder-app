import type { PartLike } from "@veupathdb/assistant-client";

/**
 * The structural shape a part is read through when the caller gets either an
 * AI SDK part (`data-<kind>`) or an assistant-ui part (`{type: "data", name}`).
 */
export interface StructuralPart {
  type: string;
  name?: string | undefined;
  data?: unknown;
}

/**
 * The same part under the protocol's own kind, which the client's readers take.
 * An assistant-ui data part names its kind separately from its type.
 */
export function protocolPart(part: StructuralPart): PartLike {
  const type =
    part.type === "data" && part.name !== undefined ? `data-${part.name}` : part.type;
  return { type, data: part.data };
}
