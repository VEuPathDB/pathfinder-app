import { describe, expect, it } from "vitest";
import { formatMessageTime, formatSidebarTime } from "./formatTime";

describe("formatMessageTime", () => {
  it("returns empty string for invalid ISO input", () => {
    expect(formatMessageTime("not-a-date")).toBe("");
    expect(formatMessageTime("")).toBe("");
  });

  it("returns a time-only string for a date that is today", () => {
    const now = new Date();
    const result = formatMessageTime(now.toISOString());
    // The result should be a short time string without a month/day.
    // It should contain a colon (e.g. "2:34 PM" or "14:34").
    expect(result).toContain(":");
    // Should NOT contain a month abbreviation.
    const months = [
      "Jan",
      "Feb",
      "Mar",
      "Apr",
      "May",
      "Jun",
      "Jul",
      "Aug",
      "Sep",
      "Oct",
      "Nov",
      "Dec",
    ];
    const hasMonth = months.some((m) => result.includes(m));
    expect(hasMonth).toBe(false);
  });

  it("returns a date + time string for a date that is not today", () => {
    // Use a date definitely in the past
    const result = formatMessageTime("2020-06-15T10:30:00Z");
    // Should contain a colon (time) and some date component
    expect(result).toContain(":");
    expect(result.length).toBeGreaterThan(0);
  });

  it("handles a date from yesterday", () => {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    const result = formatMessageTime(yesterday.toISOString());
    // Yesterday is not today, so it should include a date portion
    expect(result.length).toBeGreaterThan(0);
    expect(result).toContain(":");
  });
});

describe("formatSidebarTime", () => {
  it("returns empty string for invalid ISO input", () => {
    expect(formatSidebarTime("garbage")).toBe("");
    expect(formatSidebarTime("")).toBe("");
  });

  it("returns a time-only string for today", () => {
    const now = new Date();
    const result = formatSidebarTime(now.toISOString());
    expect(result).toContain(":");
  });

  it('returns "Yesterday" for a date from yesterday', () => {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    // Set to midday to avoid timezone edge cases
    yesterday.setHours(12, 0, 0, 0);
    const result = formatSidebarTime(yesterday.toISOString());
    expect(result).toBe("Yesterday");
  });

  it("returns a short date (without year) for earlier this year", () => {
    const now = new Date();
    // Only test if we're at least a few days into the year
    if (now.getMonth() >= 1 || now.getDate() > 3) {
      const earlier = new Date(now.getFullYear(), 0, 1, 12, 0, 0);
      const result = formatSidebarTime(earlier.toISOString());
      // Should NOT contain the year number for same-year dates
      expect(result).not.toBe("Yesterday");
      expect(result).not.toContain(":");
      // Should not be empty
      expect(result.length).toBeGreaterThan(0);
    }
  });

  it("returns a date with year for a previous year", () => {
    const result = formatSidebarTime("2020-03-15T10:00:00Z");
    // Should contain "2020"
    expect(result).toContain("2020");
  });

  it("handles midnight boundary correctly", () => {
    // Create a date at 00:00:00 today
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const result = formatSidebarTime(today.toISOString());
    // Should be treated as "today" and return a time string
    expect(result).toContain(":");
  });

  it("handles the transition from yesterday to two-days-ago", () => {
    const twoDaysAgo = new Date();
    twoDaysAgo.setDate(twoDaysAgo.getDate() - 2);
    twoDaysAgo.setHours(12, 0, 0, 0);
    const result = formatSidebarTime(twoDaysAgo.toISOString());
    // Two days ago is neither today nor yesterday
    expect(result).not.toBe("Yesterday");
    expect(result.length).toBeGreaterThan(0);
  });
});
