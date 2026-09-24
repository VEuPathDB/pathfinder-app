/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import type { RecordAttribute } from "@pathfinder/shared/generated/types/RecordAttribute";
import {
  appQueryClientWrapper,
  appTestQueryClient,
} from "@/app/components/__fixtures__/appQueryClient";

const toastError = vi.fn();
vi.mock("sonner", () => ({ toast: { error: (m: string) => toastError(m) } }));

const mockGetAttributes = vi.fn();
const mockGetRecords = vi.fn();
const mockGetRecordDetail = vi.fn();

vi.mock("@/features/workbench/analysis/api/stepResults", () => ({
  getAttributes: (...args: unknown[]) => mockGetAttributes(...args),
  getRecords: (...args: unknown[]) => mockGetRecords(...args),
  getRecordDetail: (...args: unknown[]) => mockGetRecordDetail(...args),
}));

import { ResultsTable } from "./index";

const ENTITY = { type: "gene-set", id: "gs-1" } as const;

const GENE_ID: RecordAttribute = {
  name: "gene_id",
  displayName: "Gene ID",
  help: null,
  type: null,
  isDisplayable: true,
  isSortable: true,
  isSuggested: false,
};

const RECORDS = {
  records: [
    {
      id: [{ name: "source_id", value: "PF3D7_0100100" }],
      attributes: { gene_id: "PF3D7_0100100" },
    },
  ],
  meta: {
    totalCount: 1,
    displayTotalCount: 1,
    responseCount: 1,
    pagination: { offset: 0, numRecords: 25 },
    attributes: ["gene_id"],
    tables: [],
  },
};

beforeEach(() => {
  mockGetAttributes.mockReset();
  mockGetRecords.mockReset();
  mockGetRecordDetail.mockReset();
});

describe("ResultsTable errors", () => {
  it("reports a failed attribute read once, with no toast", async () => {
    mockGetAttributes.mockRejectedValue(new Error("attribute read failed"));
    render(<ResultsTable entityRef={ENTITY} />, { wrapper: appQueryClientWrapper() });

    expect(await screen.findByText("attribute read failed")).toBeVisible();
    expect(screen.getAllByText("attribute read failed")).toHaveLength(1);
    expect(toastError).not.toHaveBeenCalled();
  });

  it("reads the attributes again on Retry after a failed attribute read", async () => {
    mockGetAttributes
      .mockRejectedValueOnce(new Error("attribute read failed"))
      .mockResolvedValue({ attributes: [GENE_ID], recordType: "gene" });
    mockGetRecords.mockResolvedValue(RECORDS);
    render(<ResultsTable entityRef={ENTITY} />, { wrapper: appQueryClientWrapper() });

    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));

    expect(await screen.findByText("PF3D7_0100100")).toBeVisible();
    expect(mockGetAttributes).toHaveBeenCalledTimes(2);
  });

  it("reports a failed records read once, with no toast", async () => {
    mockGetAttributes.mockResolvedValue({ attributes: [GENE_ID], recordType: "gene" });
    mockGetRecords.mockRejectedValue(new Error("records read failed"));
    render(<ResultsTable entityRef={ENTITY} />, { wrapper: appQueryClientWrapper() });

    expect(await screen.findByText("records read failed")).toBeVisible();
    expect(screen.getAllByText("records read failed")).toHaveLength(1);
    expect(toastError).not.toHaveBeenCalled();
  });

  it("keeps the rows and reports a failed reread of the same page once", async () => {
    mockGetAttributes.mockResolvedValue({ attributes: [GENE_ID], recordType: "gene" });
    mockGetRecords
      .mockResolvedValueOnce(RECORDS)
      .mockRejectedValue(new Error("records reread failed"));
    const client = appTestQueryClient();
    render(<ResultsTable entityRef={ENTITY} />, {
      wrapper: appQueryClientWrapper(client),
    });
    expect(await screen.findByText("PF3D7_0100100")).toBeVisible();

    await act(() => client.refetchQueries({ queryKey: ["experiments", "records"] }));

    expect(await screen.findByRole("alert")).toHaveTextContent("records reread failed");
    expect(screen.getByText("PF3D7_0100100")).toBeVisible();
    expect(toastError).not.toHaveBeenCalled();
  });

  it("reports a failed record detail read once in the open row, with no toast", async () => {
    mockGetAttributes.mockResolvedValue({ attributes: [GENE_ID], recordType: "gene" });
    mockGetRecords.mockResolvedValue(RECORDS);
    mockGetRecordDetail.mockRejectedValue(new Error("detail read failed"));
    render(<ResultsTable entityRef={ENTITY} />, { wrapper: appQueryClientWrapper() });

    fireEvent.click(await screen.findByText("PF3D7_0100100"));

    const detail = (await screen.findByText("Record Detail - PF3D7_0100100"))
      .parentElement?.parentElement;
    if (detail == null) throw new Error("the open row has no detail panel");
    expect(await within(detail).findByText("detail read failed")).toBeVisible();
    expect(screen.getAllByText("detail read failed")).toHaveLength(1);
    expect(toastError).not.toHaveBeenCalled();
  });
});
