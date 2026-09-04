/**
 * The structural shape a part is read through when the caller gets either an
 * AI SDK part (`data-<kind>`) or an assistant-ui part (`{type: "data", name}`).
 */
export interface StructuralPart {
  type: string;
  name?: string | undefined;
  data?: unknown;
}
