// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import type { ParamSpec } from "@strategist/shared";
import { DatasetParam } from "./DatasetParam";
import { http, HttpResponse } from "msw";
import { appQueryClientWrapper } from "@/app/components/__fixtures__/appQueryClient";
import { useSessionStore } from "@/state/useSessionStore";
import { server } from "../../../../../vitest.msw-setup";
import { WidgetTestForm } from "./testUtils";

afterEach(cleanup);

const SAVED_ID = "330713700";

function makeSpec(overrides: Partial<ParamSpec> = {}): ParamSpec {
  return {
    name: "test_dataset",
    type: "input-dataset",
    displayName: "Test Dataset",
    displayType: "",
    allowEmptyValue: true,
    isVisible: true,
    isNumber: false,
    countOnlyLeaves: false,
    ...overrides,
  };
}

function renderDataset(defaultValue = "", spec: ParamSpec = makeSpec()) {
  render(
    <WidgetTestForm name="test_dataset" defaultValue={defaultValue}>
      {(field) => (
        <>
          <DatasetParam
            spec={spec}
            name="test_dataset"
            options={[]}
            vocabTree={null}
            field={field}
          />
          <output data-testid="committed">{String(field.state.value)}</output>
        </>
      )}
    </WidgetTestForm>,
    { wrapper: appQueryClientWrapper() },
  );
}

function serveSavedDatasets(): unknown[] {
  const saved: unknown[] = [];
  server.use(
    http.post("*/api/v1/sites/plasmodb/datasets", async ({ request }) => {
      saved.push(await request.json());
      return HttpResponse.json({ datasetId: SAVED_ID });
    }),
  );
  return saved;
}

async function committed(value: string) {
  expect(await screen.findByText(value, { selector: "output" })).toBeTruthy();
}

beforeEach(() => {
  useSessionStore.getState().setSelectedSite("plasmodb");
});

describe("DatasetParam - empty value", () => {
  it("renders without throwing for empty string value", () => {
    renderDataset();
    expect(screen.getByRole("tablist")).toBeVisible();
  });

  it("defaults to the 'Paste IDs' tab", () => {
    renderDataset();
    const pasteTab = screen.getByRole("tab", { name: /paste ids/i });
    expect(pasteTab.getAttribute("data-state")).toBe("active");
  });

  it("shows '0 IDs' summary when paste tab is empty", () => {
    renderDataset();
    expect(screen.getByText("0 IDs")).toBeVisible();
  });
});

describe("DatasetParam - paste IDs", () => {
  it("parses newline-separated IDs from the paste textarea", async () => {
    const user = userEvent.setup();
    renderDataset();
    const textarea = screen.getByRole("textbox", { name: /paste ids/i });
    await user.type(textarea, "PF3D7_0100100\nPF3D7_0100200");
    expect(screen.getByText("2 IDs")).toBeVisible();
  });

  it("parses comma-separated IDs from the paste textarea", async () => {
    const user = userEvent.setup();
    renderDataset();
    const textarea = screen.getByRole("textbox", { name: /paste ids/i });
    await user.type(textarea, "A, B, C");
    expect(screen.getByText("3 IDs")).toBeVisible();
  });

  it("saves the pasted IDs as one list and commits its dataset id", async () => {
    const saved = serveSavedDatasets();
    const user = userEvent.setup();
    renderDataset();
    await user.type(
      screen.getByRole("textbox", { name: /paste ids/i }),
      "PF3D7_0100100\nPF3D7_0200200",
    );
    await user.tab();

    await committed(SAVED_ID);
    expect(saved).toEqual([
      {
        sourceType: "idList",
        sourceContent: { ids: ["PF3D7_0100100", "PF3D7_0200200"] },
      },
    ]);
  });

  it("keeps the saved list and posts nothing when the pasted text holds no IDs", async () => {
    const saved = serveSavedDatasets();
    const user = userEvent.setup();
    renderDataset(SAVED_ID);
    await user.type(screen.getByRole("textbox", { name: /paste ids/i }), " , ");
    await user.tab();

    expect(screen.getByTestId("committed")).toHaveTextContent(SAVED_ID);
    expect(saved).toEqual([]);
  });

  it("keeps the saved list when an empty basket loses focus", async () => {
    const saved = serveSavedDatasets();
    const user = userEvent.setup();
    renderDataset(SAVED_ID);
    await user.click(screen.getByRole("tab", { name: /basket/i }));
    await user.click(screen.getByRole("textbox", { name: "Basket record type" }));
    await user.tab();

    expect(screen.getByTestId("committed")).toHaveTextContent(SAVED_ID);
    expect(saved).toEqual([]);
  });

  it("posts the same pasted list once across two blurs", async () => {
    const saved = serveSavedDatasets();
    const user = userEvent.setup();
    renderDataset();
    const textarea = screen.getByRole("textbox", { name: /paste ids/i });
    await user.type(textarea, "PF3D7_0100100");
    await user.tab();
    await committed(SAVED_ID);
    await user.click(textarea);
    await user.tab();

    expect(saved).toHaveLength(1);
  });

  it("commits the id of the latest list when the earlier save answers last", async () => {
    const answers: Array<() => void> = [];
    let next = 0;
    server.use(
      http.post("*/api/v1/sites/plasmodb/datasets", async () => {
        const datasetId = ["111", "222"][next++] ?? "0";
        await new Promise<void>((resolve) => answers.push(resolve));
        return HttpResponse.json({ datasetId });
      }),
    );
    const user = userEvent.setup();
    renderDataset();
    const textarea = screen.getByRole("textbox", { name: /paste ids/i });
    await user.type(textarea, "PF3D7_0100100");
    await user.tab();
    await user.type(textarea, ",PF3D7_0200200");
    await user.tab();
    await waitFor(() => expect(answers).toHaveLength(2));
    answers[1]?.();
    await committed("222");
    answers[0]?.();

    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByTestId("committed")).toHaveTextContent("222");
  });

  it("posts a refused list again on the next blur", async () => {
    let posts = 0;
    server.use(
      http.post("*/api/v1/sites/plasmodb/datasets", () => {
        posts += 1;
        return HttpResponse.json(
          {
            title: "Dataset not saved",
            status: 502,
            detail: "The site did not answer.",
          },
          { status: 502, headers: { "Content-Type": "application/problem+json" } },
        );
      }),
    );
    const user = userEvent.setup();
    renderDataset();
    const textarea = screen.getByRole("textbox", { name: /paste ids/i });
    await user.type(textarea, "PF3D7_0100100");
    await user.tab();
    await screen.findByRole("alert");
    await user.click(textarea);
    await user.tab();

    await waitFor(() => expect(posts).toBe(2));
  });

  it("names the save the site refused and keeps the value", async () => {
    server.use(
      http.post("*/api/v1/sites/plasmodb/datasets", () =>
        HttpResponse.json(
          {
            title: "Dataset not saved",
            status: 422,
            detail: "The site refused the list.",
          },
          { status: 422, headers: { "Content-Type": "application/problem+json" } },
        ),
      ),
    );
    const user = userEvent.setup();
    renderDataset("223588743");
    await user.type(
      screen.getByRole("textbox", { name: /paste ids/i }),
      "PF3D7_0100100",
    );
    await user.tab();

    expect(await screen.findByRole("alert")).toBeVisible();
    expect(screen.getByTestId("committed")).toHaveTextContent("223588743");
  });
});

describe("DatasetParam - basket / strategy tabs", () => {
  it("switches to the Basket tab when clicked", async () => {
    const user = userEvent.setup();
    renderDataset();
    await user.click(screen.getByRole("tab", { name: /basket/i }));
    expect(
      screen.getByRole("tab", { name: /basket/i }).getAttribute("data-state"),
    ).toBe("active");
  });

  it("saves the basket of the record type the researcher names", async () => {
    const saved = serveSavedDatasets();
    const user = userEvent.setup();
    renderDataset();
    await user.click(screen.getByRole("tab", { name: /basket/i }));
    await user.type(
      screen.getByRole("textbox", { name: "Basket record type" }),
      "transcript",
    );
    await user.tab();

    await committed(SAVED_ID);
    expect(saved).toEqual([
      { sourceType: "basket", sourceContent: { basketName: "transcript" } },
    ]);
    expect(
      screen.getByText(
        "The site reads the records in your basket of this type; genes are transcript.",
      ),
    ).toBeVisible();
  });

  it("posts the basket record type without its surrounding spaces", async () => {
    const saved = serveSavedDatasets();
    const user = userEvent.setup();
    renderDataset();
    await user.click(screen.getByRole("tab", { name: /basket/i }));
    await user.type(
      screen.getByRole("textbox", { name: "Basket record type" }),
      "transcript ",
    );
    await user.tab();

    await committed(SAVED_ID);
    expect(saved).toEqual([
      { sourceType: "basket", sourceContent: { basketName: "transcript" } },
    ]);
  });

  it("saves the strategy the researcher picks", async () => {
    const saved = serveSavedDatasets();
    server.use(
      http.get("*/api/v1/conversations", () =>
        HttpResponse.json([
          {
            id: "5b0c1d2e-0000-4000-8000-000000000001",
            name: "Kinases",
            siteId: "plasmodb",
            recordType: "transcript",
            createdAt: "2026-09-24T00:00:00Z",
            updatedAt: "2026-09-24T00:00:00Z",
            wdkStrategyId: 330713643,
          },
        ]),
      ),
    );
    const user = userEvent.setup();
    renderDataset();
    await user.click(screen.getByRole("tab", { name: /strategy/i }));
    await user.click(await screen.findByRole("combobox"));
    await user.click(await screen.findByText("Kinases"));

    await committed(SAVED_ID);
    expect(saved).toEqual([
      { sourceType: "strategy", sourceContent: { strategyId: 330713643 } },
    ]);
  });
});

describe("DatasetParam - file upload", () => {
  it("shows file upload tab and accepts a file", async () => {
    serveSavedDatasets();
    const user = userEvent.setup();
    renderDataset();
    await user.click(screen.getByRole("tab", { name: /upload/i }));
    const fileInput = screen.getByLabelText(/upload file/i);
    if (!(fileInput instanceof HTMLInputElement)) {
      throw new Error("Expected the upload input to be an HTMLInputElement");
    }
    expect(fileInput.type).toBe("file");
    const file = new File(["PF3D7_0100100\nPF3D7_0200200"], "ids.txt", {
      type: "text/plain",
    });
    fireEvent.change(fileInput, { target: { files: [file] } });
    expect(await screen.findByText("ids.txt")).toBeVisible();
  });

  it("saves the file's gene IDs as the same list the Paste tab saves", async () => {
    const saved = serveSavedDatasets();
    const user = userEvent.setup();
    renderDataset();
    await user.click(screen.getByRole("tab", { name: /upload/i }));
    const csv = [
      "gene_id,product",
      "PF3D7_1133400,apical membrane antigen 1",
      "PF3D7_0709000,chloroquine resistance transporter",
      "PF3D7_0100100,erythrocyte membrane protein 1",
      "PF3D7_1133400,apical membrane antigen 1",
    ].join("\n");
    const file = new File([csv], "ids.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText(/upload file/i), {
      target: { files: [file] },
    });

    expect(await screen.findByText("ids.csv")).toBeVisible();
    await committed(SAVED_ID);
    expect(saved).toEqual([
      {
        sourceType: "idList",
        sourceContent: { ids: ["PF3D7_1133400", "PF3D7_0709000", "PF3D7_0100100"] },
      },
    ]);
    expect(screen.getByText("3 IDs")).toBeVisible();
  });
});

describe("DatasetParam - default id list", () => {
  const withDefault = makeSpec({
    initialDisplayValue: JSON.stringify({
      sourceType: "idList",
      sourceContent: { ids: ["PF3D7_DEFAULT_001"] },
    }),
  });

  it("does not render Default list tab when defaultIdList is absent", () => {
    renderDataset();
    expect(screen.queryAllByRole("tab", { name: /default/i })).toHaveLength(0);
    expect(screen.getByRole("tab", { name: /paste ids/i })).toBeVisible();
  });

  it("renders Default list tab when spec.initialDisplayValue is a default id list string", () => {
    renderDataset("", withDefault);
    expect(screen.getByRole("tab", { name: "Default" })).toBeVisible();
  });

  it("saves the default list when the researcher uses it", async () => {
    const saved = serveSavedDatasets();
    const user = userEvent.setup();
    renderDataset("", withDefault);
    await user.click(screen.getByRole("button", { name: "Use this" }));

    await committed(SAVED_ID);
    expect(saved).toEqual([
      { sourceType: "idList", sourceContent: { ids: ["PF3D7_DEFAULT_001"] } },
    ]);
  });

  it("paints the unrecognized-value notice from the warning token", () => {
    renderDataset("not-a-dataset-config");
    const notice = screen.getByText(
      "This value is not an ID list the editor reads. Paste or upload IDs to replace it.",
    );
    expect(notice).toHaveClass("text-warning");
    expect(notice.className).not.toContain("amber");
  });

  it("names the saved ID list a step built on the site reads", () => {
    renderDataset("223588743");
    expect(
      screen.getByText(
        "This step reads saved ID list 223588743 on the site. Paste or upload IDs to replace it.",
      ),
    ).toBeVisible();
    expect(screen.queryByText(/DatasetConfig/)).toBeNull();
  });
});

describe("DatasetParam - read-only", () => {
  it("does not open the strategy list when the widget is disabled", async () => {
    server.use(
      http.get("*/api/v1/conversations", () =>
        HttpResponse.json([
          {
            id: "5b0c1d2e-0000-4000-8000-000000000001",
            name: "Kinases",
            siteId: "plasmodb",
            recordType: "transcript",
            createdAt: "2026-09-24T00:00:00Z",
            updatedAt: "2026-09-24T00:00:00Z",
            wdkStrategyId: 330713643,
          },
        ]),
      ),
    );
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <WidgetTestForm name="test_dataset" defaultValue="">
        {(field) => (
          <DatasetParam
            spec={makeSpec({ isReadOnly: true })}
            name="test_dataset"
            options={[]}
            vocabTree={null}
            field={{ ...field, handleChange: onChange }}
            disabled
          />
        )}
      </WidgetTestForm>,
      { wrapper: appQueryClientWrapper() },
    );

    await user.click(screen.getByRole("tab", { name: /strategy/i }));
    const trigger = await screen.findByRole("combobox");
    await user.click(trigger);

    expect(trigger).toBeDisabled();
    expect(screen.queryByText("Kinases")).toBe(null);
    expect(onChange.mock.calls).toEqual([]);
  });
});
