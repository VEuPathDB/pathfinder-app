import type { ComponentType } from "react";
import type { DataPartPayloadMap, KnownDataPartKind } from "@strategist/shared";

/** A renderer for every kind in `K`, each typed to that kind's payload. */
export type DataPartComponentMap<K extends KnownDataPartKind> = {
  [Kind in K]: ComponentType<{ data: DataPartPayloadMap[Kind] }>;
};
