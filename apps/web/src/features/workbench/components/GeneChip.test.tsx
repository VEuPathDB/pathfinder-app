// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { GeneChip } from "./GeneChip";
import type { ResolvedGene } from "@pathfinder/shared";

const RESOLVED: ResolvedGene = {
  geneId: "PF3D7_0100100",
  displayName: "PF3D7_0100100",
  organism: "Plasmodium falciparum 3D7",
  product: "erythrocyte membrane protein 1, PfEMP1",
  geneName: "VAR",
  geneType: "protein_coding",
  location: "Pf3D7_01_v3:29510-37126(+)",
};

describe("GeneChip", () => {
  afterEach(cleanup);

  it("renders gene ID text", () => {
    render(<GeneChip geneId="PF3D7_0100100" status="pending" onRemove={() => {}} />);
    expect(screen.getByText("PF3D7_0100100")).toBeTruthy();
  });

  it("shows remove button that calls onRemove", () => {
    const onRemove = vi.fn();
    render(<GeneChip geneId="PF3D7_0100100" status="verified" onRemove={onRemove} />);
    fireEvent.click(screen.getByRole("button", { name: /remove/i }));
    expect(onRemove).toHaveBeenCalledWith("PF3D7_0100100");
  });

  it("applies verified styling when status is verified", () => {
    const { container } = render(
      <GeneChip geneId="PF3D7_0100100" status="verified" onRemove={() => {}} />,
    );
    expect(container.querySelector("[data-gene-chip]")).toHaveAttribute(
      "data-status",
      "verified",
    );
  });

  it("applies invalid styling when status is invalid", () => {
    const { container } = render(
      <GeneChip geneId="INVALID_001" status="invalid" onRemove={() => {}} />,
    );
    expect(container.querySelector("[data-gene-chip]")).toHaveAttribute(
      "data-status",
      "invalid",
    );
  });

  it("shows rich hover card with gene details when resolvedGene is provided", async () => {
    const { container } = render(
      <GeneChip
        geneId="PF3D7_0100100"
        status="verified"
        resolvedGene={RESOLVED}
        onRemove={() => {}}
      />,
    );
    const chip = container.querySelector("[data-gene-chip]")!;
    fireEvent.mouseEnter(chip);
    await waitFor(() => {
      expect(screen.getByText("erythrocyte membrane protein 1, PfEMP1")).toBeTruthy();
      expect(screen.getByText("Plasmodium falciparum 3D7")).toBeTruthy();
      expect(screen.getByText("protein_coding")).toBeTruthy();
    });
  });

  it("animates in with scale transition", () => {
    const { container } = render(
      <GeneChip geneId="PF3D7_0100100" status="pending" onRemove={() => {}} />,
    );
    const chip = container.querySelector("[data-gene-chip]");
    expect(chip?.className).toContain("animate-chip-in");
  });
});
