// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import type { ParamSpec } from "@pathfinder/shared";
import { DatasetParam } from "./DatasetParam";
import { WidgetTestForm } from "./testUtils";

afterEach(cleanup);

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

describe("DatasetParam - empty value", () => {
  it("renders without throwing for empty string value", () => {
    render(
      <WidgetTestForm name="test_dataset" defaultValue="">
        {(field) => (
          <DatasetParam
            spec={makeSpec()}
            name="test_dataset"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByRole("tablist")).toBeVisible();
  });

  it("defaults to the 'Paste IDs' tab", () => {
    render(
      <WidgetTestForm name="test_dataset" defaultValue="">
        {(field) => (
          <DatasetParam
            spec={makeSpec()}
            name="test_dataset"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    const pasteTab = screen.getByRole("tab", { name: /paste ids/i });
    expect(pasteTab.getAttribute("data-state")).toBe("active");
  });

  it("shows '0 IDs' summary when paste tab is empty", () => {
    render(
      <WidgetTestForm name="test_dataset" defaultValue="">
        {(field) => (
          <DatasetParam
            spec={makeSpec()}
            name="test_dataset"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByText("0 IDs")).toBeVisible();
  });
});

describe("DatasetParam - paste IDs", () => {
  it("parses newline-separated IDs from the paste textarea", async () => {
    const user = userEvent.setup();
    render(
      <WidgetTestForm name="test_dataset" defaultValue="">
        {(field) => (
          <DatasetParam
            spec={makeSpec()}
            name="test_dataset"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    const textarea = screen.getByRole("textbox", { name: /paste ids/i });
    await user.type(textarea, "PF3D7_0100100\nPF3D7_0100200");
    expect(screen.getByText("2 IDs")).toBeVisible();
  });

  it("parses comma-separated IDs from the paste textarea", async () => {
    const user = userEvent.setup();
    render(
      <WidgetTestForm name="test_dataset" defaultValue="">
        {(field) => (
          <DatasetParam
            spec={makeSpec()}
            name="test_dataset"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    const textarea = screen.getByRole("textbox", { name: /paste ids/i });
    await user.type(textarea, "A, B, C");
    expect(screen.getByText("3 IDs")).toBeVisible();
  });

  it("hydrates the paste textarea from an existing idList value", () => {
    const value = JSON.stringify({
      sourceType: "idList",
      sourceContent: { ids: ["PF3D7_0100100", "PF3D7_0200200"] },
    });
    render(
      <WidgetTestForm name="test_dataset" defaultValue={value}>
        {(field) => (
          <DatasetParam
            spec={makeSpec()}
            name="test_dataset"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByRole("textbox", { name: "Paste IDs" })).toHaveValue(
      "PF3D7_0100100\nPF3D7_0200200",
    );
  });
});

describe("DatasetParam - basket / strategy tabs", () => {
  it("switches to the Basket tab when clicked", async () => {
    const user = userEvent.setup();
    render(
      <WidgetTestForm name="test_dataset" defaultValue="">
        {(field) => (
          <DatasetParam
            spec={makeSpec()}
            name="test_dataset"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    await user.click(screen.getByRole("tab", { name: /basket/i }));
    expect(
      screen.getByRole("tab", { name: /basket/i }).getAttribute("data-state"),
    ).toBe("active");
  });

  it("commits the basket of the record type the researcher names", async () => {
    const user = userEvent.setup();
    render(
      <WidgetTestForm name="test_dataset" defaultValue="">
        {(field) => (
          <>
            <DatasetParam
              spec={makeSpec()}
              name="test_dataset"
              options={[]}
              vocabTree={null}
              field={field}
            />
            <output data-testid="committed">{String(field.state.value)}</output>
          </>
        )}
      </WidgetTestForm>,
    );
    await user.click(screen.getByRole("tab", { name: /basket/i }));
    const basketInput = screen.getByRole("textbox", { name: "Basket record type" });
    await user.type(basketInput, "transcript");
    expect(JSON.parse(screen.getByTestId("committed").textContent)).toEqual({
      sourceType: "basket",
      sourceContent: { basketName: "transcript" },
    });
    expect(
      screen.getByText(
        "The site reads the records in your basket of this type; genes are transcript.",
      ),
    ).toBeVisible();
  });
});

describe("DatasetParam - file upload", () => {
  it("shows file upload tab and accepts a file", async () => {
    const user = userEvent.setup();
    render(
      <WidgetTestForm name="test_dataset" defaultValue="">
        {(field) => (
          <DatasetParam
            spec={makeSpec()}
            name="test_dataset"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
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

  it("commits the file's gene IDs as the same idList payload the Paste tab sends", async () => {
    const user = userEvent.setup();
    render(
      <WidgetTestForm name="test_dataset" defaultValue="">
        {(field) => (
          <>
            <DatasetParam
              spec={makeSpec()}
              name="test_dataset"
              options={[]}
              vocabTree={null}
              field={field}
            />
            <output data-testid="committed">{String(field.state.value)}</output>
          </>
        )}
      </WidgetTestForm>,
    );
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
    expect(JSON.parse(screen.getByTestId("committed").textContent)).toEqual({
      sourceType: "idList",
      sourceContent: { ids: ["PF3D7_1133400", "PF3D7_0709000", "PF3D7_0100100"] },
    });
    expect(screen.getByText("3 IDs")).toBeVisible();
  });
});

describe("DatasetParam - default id list", () => {
  it("does not render Default list tab when defaultIdList is absent", () => {
    render(
      <WidgetTestForm name="test_dataset" defaultValue="">
        {(field) => (
          <DatasetParam
            spec={makeSpec()}
            name="test_dataset"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.queryAllByRole("tab", { name: /default/i })).toHaveLength(0);
    expect(screen.getByRole("tab", { name: /paste ids/i })).toBeVisible();
  });

  it("renders Default list tab when spec.initialDisplayValue is a default id list string", () => {
    const spec = makeSpec({
      initialDisplayValue: JSON.stringify({
        sourceType: "idList",
        sourceContent: { ids: ["PF3D7_DEFAULT_001"] },
      }),
    });
    render(
      <WidgetTestForm name="test_dataset" defaultValue="">
        {(field) => (
          <DatasetParam
            spec={spec}
            name="test_dataset"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(screen.getByRole("tab", { name: "Default" })).toBeVisible();
  });

  it("paints the unrecognized-value notice from the warning token", () => {
    render(
      <WidgetTestForm name="test_dataset" defaultValue="not-a-dataset-config">
        {(field) => (
          <DatasetParam
            spec={makeSpec()}
            name="test_dataset"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    const notice = screen.getByText(
      "This value is not an ID list the editor reads. Paste or upload IDs to replace it.",
    );
    expect(notice).toHaveClass("text-warning");
    expect(notice.className).not.toContain("amber");
  });

  it("names the saved ID list a step built on the site reads", () => {
    render(
      <WidgetTestForm name="test_dataset" defaultValue="223588743">
        {(field) => (
          <DatasetParam
            spec={makeSpec()}
            name="test_dataset"
            options={[]}
            vocabTree={null}
            field={field}
          />
        )}
      </WidgetTestForm>,
    );
    expect(
      screen.getByText(
        "This step reads saved ID list 223588743 on the site. Paste or upload IDs to replace it.",
      ),
    ).toBeVisible();
    expect(screen.queryByText(/DatasetConfig/)).toBeNull();
  });
});
