import type { DataMessagePartComponent } from "@assistant-ui/react";

import { dataPartComponents } from "./contentComponents";

const DATA_PREFIX = "data-" as const;

const registry: Record<string, DataMessagePartComponent<unknown>> = {};
for (const [kind, Component] of Object.entries(dataPartComponents)) {
  const shortName = kind.startsWith(DATA_PREFIX)
    ? kind.slice(DATA_PREFIX.length)
    : kind;
  registry[shortName] = Component as DataMessagePartComponent<unknown>;
}

/** Data-part renderers keyed by the part name assistant-ui reports (no `data-` prefix). */
export const dataPartRenderers: Readonly<
  Record<string, DataMessagePartComponent<unknown>>
> = registry;
