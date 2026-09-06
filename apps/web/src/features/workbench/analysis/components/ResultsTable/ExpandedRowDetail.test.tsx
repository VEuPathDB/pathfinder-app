/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, it, expect } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ExpandedRowDetail } from "./ExpandedRowDetail";
import type { RecordDetailResponse } from "@pathfinder/shared/generated/types/RecordDetailResponse";

describe("ExpandedRowDetail", () => {
  afterEach(cleanup);

  const baseProps = {
    pk: "PF3D7_0102600",
    error: null,
    loading: false,
    onClose: () => {},
  };

  it("renders attribute values using display names from attributeNames", () => {
    const detail: RecordDetailResponse = {
      displayName: "PF3D7_0102600",
      id: [{ name: "source_id", value: "PF3D7_0102600" }],
      recordClassName: "TranscriptRecordClasses.TranscriptRecordClass",
      attributes: {
        gene_product: "serine/threonine protein kinase",
        organism: "Plasmodium falciparum 3D7",
      },
      attributeNames: {
        gene_product: "Product Description",
        organism: "Organism",
      },
      tables: {},
      tableErrors: [],
    };

    render(<ExpandedRowDetail {...baseProps} detail={detail} />);

    // Should use display name, not raw field name
    expect(screen.getByText("Product Description")).toBeTruthy();
    expect(screen.getByText("Organism")).toBeTruthy();
    // Should render values
    expect(screen.getByText("serine/threonine protein kinase")).toBeTruthy();
    expect(screen.getByText("Plasmodium falciparum 3D7")).toBeTruthy();
  });

  it("falls back to raw field name when attributeNames has no match", () => {
    const detail: RecordDetailResponse = {
      displayName: "PF3D7_0102600",
      id: [{ name: "source_id", value: "PF3D7_0102600" }],
      recordClassName: "TranscriptRecordClasses.TranscriptRecordClass",
      attributes: {
        gene_product: "kinase",
      },
      attributeNames: {},
      tables: {},
      tableErrors: [],
    };

    render(<ExpandedRowDetail {...baseProps} detail={detail} />);

    expect(screen.getByText("gene_product")).toBeTruthy();
    expect(screen.getByText("kinase")).toBeTruthy();
  });

  it("shows loading state", () => {
    render(<ExpandedRowDetail {...baseProps} detail={null} loading />);

    expect(screen.getByText("Loading details...")).toBeTruthy();
  });

  it("shows error state", () => {
    render(<ExpandedRowDetail {...baseProps} detail={null} error="Request failed" />);

    expect(screen.getByText("Request failed")).toBeTruthy();
  });

  it("shows fallback when detail has no attributes", () => {
    const detail: RecordDetailResponse = {
      displayName: "PF3D7_0102600",
      id: [{ name: "source_id", value: "PF3D7_0102600" }],
      recordClassName: "TranscriptRecordClasses.TranscriptRecordClass",
      attributes: {},
      attributeNames: {},
      tables: {},
      tableErrors: [],
    };

    render(<ExpandedRowDetail {...baseProps} detail={detail} />);

    expect(screen.getByText("Unable to load details.")).toBeTruthy();
  });
});
