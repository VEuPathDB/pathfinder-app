// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { VocabEntry } from "../../utils/paramUtils";
import { CategoricalPicker } from "./CategoricalPicker";
import { MAX_CATEGORICAL_CHOICES } from "./types";

function vocab(size: number): VocabEntry[] {
  return Array.from({ length: size }, (_, i) => ({
    value: `v${i}`,
    display: `Value ${i}`,
  }));
}

describe("CategoricalPicker", () => {
  it("warns through the warning token when the vocabulary is truncated", () => {
    render(
      <CategoricalPicker
        vocab={vocab(MAX_CATEGORICAL_CHOICES + 3)}
        selected={new Set()}
        onChange={() => {}}
      />,
    );
    const notice = screen.getByText(/Showing first/);
    expect(notice).toHaveClass("text-warning");
    expect(notice.className).not.toContain("amber");
  });

  it("shows no truncation notice when the vocabulary fits", () => {
    render(
      <CategoricalPicker vocab={vocab(3)} selected={new Set()} onChange={() => {}} />,
    );
    expect(screen.queryAllByText(/Showing first/)).toHaveLength(0);
  });
});
