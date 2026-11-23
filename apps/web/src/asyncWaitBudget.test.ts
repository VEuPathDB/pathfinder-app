import { getConfig } from "@testing-library/react";
import { describe, expect, it } from "vitest";

describe("the test setup", () => {
  it("gives every async query five seconds under a loaded machine", () => {
    expect(getConfig().asyncUtilTimeout).toBe(5000);
  });
});
