import { describe, expect, it } from "vitest";

import { dataPartComponents } from "./contentComponents";
import { auditDataPartComponents } from "./auditDataParts";
import { noRender } from "./coreDataParts";

describe("audit data parts", () => {
  it("draws the start card in the approval card, not in the message", () => {
    expect(auditDataPartComponents).toEqual({ "data-audit-start": noRender });
    expect(dataPartComponents["data-audit-start"]).toBe(noRender);
  });
});
