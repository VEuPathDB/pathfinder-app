import { describe, expect, it } from "vitest";
import { recordCountLabel } from "./recordCountLabel";

// WDK does not always publish a count. Rendering an absent count as zero states
// a result nobody measured, next to rows the reader can see.
describe("recordCountLabel", () => {
  it("names the record type when the count is known", () => {
    expect(recordCountLabel(3392, "transcript")).toBe("3,392 transcripts");
  });

  it("uses the singular for one record", () => {
    expect(recordCountLabel(1, "transcript")).toBe("1 transcript");
  });

  it("reports a genuine zero", () => {
    expect(recordCountLabel(0, "transcript")).toBe("0 transcripts");
  });

  it("does not claim zero when the count is absent", () => {
    const label = recordCountLabel(null, "transcript");

    expect(label).not.toContain("0");
    expect(label).toContain("transcript");
  });

  it("says the count is unknown when it is absent", () => {
    expect(recordCountLabel(null, "transcript")).toBe("transcripts, count unavailable");
  });

  it("falls back to records without a record type", () => {
    expect(recordCountLabel(null, null)).toBe("records, count unavailable");
  });
});
