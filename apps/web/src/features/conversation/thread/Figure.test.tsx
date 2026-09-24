/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

const toasted: string[] = [];
vi.mock("sonner", () => ({
  toast: {
    success: (message: string) => {
      toasted.push(message);
    },
  },
}));

import { Figure } from "./Figure";

const CARD_CLASSES = ["border", "rounded-lg", "rounded-md", "shadow-card"];

function classesOf(node: HTMLElement): string[] {
  return node.className.split(/\s+/).filter((token) => token !== "");
}

describe("Figure", () => {
  it("renders its children inside the figure", () => {
    render(
      <Figure title={null} caption={null}>
        <p data-testid="body">1,543 genes</p>
      </Figure>,
    );
    const figure = screen.getByTestId("figure");
    expect(figure).toContainElement(screen.getByTestId("body"));
    expect(figure.textContent).toBe("1,543 genes");
  });

  it("titles the figure with a figcaption when a title is given", () => {
    render(
      <Figure title="log2(Fold Change)" caption={null}>
        <p>body</p>
      </Figure>,
    );
    const title = screen.getByText("log2(Fold Change)");
    expect(title.tagName).toBe("FIGCAPTION");
    expect(classesOf(title)).toEqual(["mb-2", "text-sm", "font-medium"]);
  });

  it("draws no figcaption when the title is null", () => {
    const { container } = render(
      <Figure title={null} caption="1,543 of 5,511 genes retained">
        <p>body</p>
      </Figure>,
    );
    expect(container.querySelectorAll("figcaption")).toHaveLength(0);
  });

  it("carries the numbers in a caption under the body", () => {
    render(
      <Figure title={null} caption="1,543 of 5,511 genes retained">
        <p>body</p>
      </Figure>,
    );
    const caption = screen.getByTestId("figure-caption");
    expect(caption).toHaveTextContent("1,543 of 5,511 genes retained");
    expect(classesOf(caption)).toEqual(["mt-2", "text-xs", "text-muted-foreground"]);
  });

  it("centers, italicizes and numbers the caption of a numbered figure", () => {
    render(
      <Figure
        title={null}
        caption="Heat shock - 1,543 of 5,511 genes retained."
        exhibit={{ kind: "figure", number: 2 }}
      >
        <p>body</p>
      </Figure>,
    );
    const caption = screen.getByTestId("figure-caption");
    expect(caption.textContent).toBe(
      "Figure 2. Heat shock - 1,543 of 5,511 genes retained.",
    );
    expect(classesOf(caption)).toEqual([
      "mt-2",
      "text-xs",
      "text-muted-foreground",
      "text-center",
      "italic",
    ]);
  });

  it("keeps the left caption when a numbered figure has no number yet", () => {
    render(
      <Figure
        title={null}
        caption="1,543 of 5,511 genes retained."
        exhibit={{ kind: "figure", number: null }}
      >
        <p>body</p>
      </Figure>,
    );
    const caption = screen.getByTestId("figure-caption");
    expect(caption.textContent).toBe("1,543 of 5,511 genes retained.");
    expect(classesOf(caption)).toEqual(["mt-2", "text-xs", "text-muted-foreground"]);
  });

  it("numbers a table with the table counter, not the figure counter", () => {
    render(
      <Figure
        title="Control tests"
        caption="target 132 records."
        exhibit={{ kind: "table", number: 1 }}
      >
        <p>body</p>
      </Figure>,
    );
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "Table 1. target 132 records.",
    );
  });

  it("draws no numbered caption when the caption is null", () => {
    render(
      <Figure
        title="Control tests"
        caption={null}
        exhibit={{ kind: "table", number: 1 }}
      >
        <p>body</p>
      </Figure>,
    );
    expect(screen.queryByTestId("figure-caption")).toBe(null);
  });

  it("draws no caption element when the caption is null", () => {
    render(
      <Figure title="Control tests" caption={null}>
        <p>body</p>
      </Figure>,
    );
    expect(screen.queryByTestId("figure-caption")).toBe(null);
  });

  it("draws no divider, no card and no outer margin of its own", () => {
    render(
      <Figure title="Control tests" caption="2 of 3 positive controls recovered">
        <p>body</p>
      </Figure>,
    );
    const tokens = classesOf(screen.getByTestId("figure"));
    expect(tokens).toEqual([]);
    expect(tokens.filter((token) => CARD_CLASSES.includes(token))).toEqual([]);
  });

  it("orders the title, the body and the caption", () => {
    const { container } = render(
      <Figure title="Control tests" caption="2 of 3 positive controls recovered">
        <p data-testid="body">body</p>
      </Figure>,
    );
    const figure = container.querySelector("figure");
    const testIds = [...(figure?.children ?? [])].map((child) =>
      child.getAttribute("data-testid"),
    );
    expect(testIds).toEqual([null, "body", "figure-caption"]);
    expect(figure?.children[0]?.tagName).toBe("FIGCAPTION");
  });

  it("renders the footer after the caption, inside the figure", () => {
    const { container } = render(
      <Figure
        title="Control tests"
        caption="2 of 3 positive controls recovered"
        footer={<p data-testid="readout">342 of 5,511 genes</p>}
      >
        <p data-testid="body">body</p>
      </Figure>,
    );
    const figure = container.querySelector("figure");
    const testIds = [...(figure?.children ?? [])].map((child) =>
      child.getAttribute("data-testid"),
    );
    expect(testIds).toEqual([null, "body", "figure-caption", "readout"]);
  });

  it("draws no footer node when none is given", () => {
    render(
      <Figure title={null} caption="12 terms">
        <p data-testid="body">body</p>
      </Figure>,
    );
    expect(screen.queryByTestId("readout")).toBe(null);
  });

  it("names the part it draws inside the figure, title and caption with it", () => {
    render(
      <Figure
        title={null}
        caption="Title set: Malaria gene discovery"
        testId="data-conversation-title"
      >
        {null}
      </Figure>,
    );
    const named = screen.getByTestId("data-conversation-title");
    expect(named).toHaveTextContent("Title set: Malaria gene discovery");
    expect(screen.getByTestId("figure").contains(named)).toBe(true);
    expect(named.querySelectorAll('[data-testid="figure-caption"]')).toHaveLength(1);
  });
});

describe("a numbered exhibit is anchored and citable", () => {
  function renderTable() {
    return render(
      <Figure
        title="Control tests"
        caption="target 132 records."
        exhibit={{ kind: "table", number: 2 }}
      >
        <p>body</p>
      </Figure>,
    );
  }

  it("anchors the figure element on the exhibit's own id", () => {
    renderTable();
    expect(screen.getByTestId("figure").getAttribute("id")).toBe("table-2");
  });

  it("anchors a figure on the figure counter's id", () => {
    render(
      <Figure title="Volcano" caption="c." exhibit={{ kind: "figure", number: 3 }}>
        <p>body</p>
      </Figure>,
    );
    expect(screen.getByTestId("figure").getAttribute("id")).toBe("figure-3");
  });

  it("leaves an unnumbered exhibit unanchored", () => {
    render(
      <Figure title="Variants" caption="c.">
        <p>body</p>
      </Figure>,
    );
    expect(screen.getByTestId("figure").hasAttribute("id")).toBe(false);
  });

  it("copies the conversation url with the exhibit's fragment", () => {
    const written: string[] = [];
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: async (text: string) => void written.push(text) },
    });
    toasted.length = 0;
    window.history.replaceState(null, "", "/plasmodb/conversation/c1");
    renderTable();

    const control = screen.getByRole("button", { name: "Copy link to Table 2" });
    fireEvent.click(control);

    expect(written).toEqual([
      `${window.location.origin}/plasmodb/conversation/c1#table-2`,
    ]);
    expect(toasted).toEqual(["Link to Table 2 copied"]);
  });

  it("draws the citation control in the title row, beside the action", () => {
    render(
      <Figure
        title="Control tests"
        caption="c."
        exhibit={{ kind: "table", number: 2 }}
        action={<button type="button">Download</button>}
      >
        <p>body</p>
      </Figure>,
    );
    const row = screen.getByText("Control tests").parentElement;
    expect(row?.tagName).toBe("FIGCAPTION");
    expect(row).toContainElement(
      screen.getByRole("button", { name: "Copy link to Table 2" }),
    );
    expect(row).toContainElement(screen.getByRole("button", { name: "Download" }));
  });

  it("offers no citation control for an unnumbered exhibit", () => {
    render(
      <Figure title="Variants" caption="c.">
        <p>body</p>
      </Figure>,
    );
    expect(screen.queryByTestId("exhibit-citation")).toBe(null);
  });
});
