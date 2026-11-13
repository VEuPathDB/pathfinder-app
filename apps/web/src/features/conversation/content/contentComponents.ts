import type { KnownDataPartKind } from "@strategist/shared";

import { auditDataPartComponents } from "./auditDataParts";
import { coreDataPartComponents } from "./coreDataParts";
import { edaDataPartComponents } from "./edaDataParts";
import { strategyDataPartComponents } from "./strategyDataParts";
import type { DataPartComponentMap } from "./dataPartComponentMap";

// The one place the runtime map and a product map compose. A kind that no half
// covers fails to compile, because the merged object must be total over
// KnownDataPartKind. Unknown kinds are absent here and hit the fallback.
export const dataPartComponents: DataPartComponentMap<KnownDataPartKind> = {
  ...coreDataPartComponents,
  ...strategyDataPartComponents,
  ...edaDataPartComponents,
  ...auditDataPartComponents,
};
