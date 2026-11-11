import { noRender } from "./coreDataParts";
import type { DataPartComponentMap } from "./dataPartComponentMap";

export type AuditDataPartKind = "data-audit-start";

export const auditDataPartComponents: DataPartComponentMap<AuditDataPartKind> = {
  "data-audit-start": noRender,
};
