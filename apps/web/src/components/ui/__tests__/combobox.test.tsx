/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { useState } from "react";

import { Combobox, type ComboboxOption } from "@/components/ui/combobox";

const OPTIONS: ComboboxOption[] = [
  { value: "alpha", label: "Alpha" },
  { value: "beta", label: "Beta" },
  { value: "gamma", label: "Gamma" },
];

describe("Combobox (single)", () => {
  function SingleHarness() {
    const [value, setValue] = useState<string | null>(null);
    return (
      <Combobox
        options={OPTIONS}
        value={value}
        onChange={setValue}
        placeholder="Select an option"
        emptyMessage="No matches"
      />
    );
  }

  it("opens, shows options, and selects one", async () => {
    const user = userEvent.setup();
    render(<SingleHarness />);

    const trigger = screen.getByText("Select an option").closest("button");
    expect(trigger).not.toBeNull();
    await user.click(trigger!);

    expect(await screen.findByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();

    await user.click(screen.getByText("Beta"));

    expect(screen.getByText("Beta")).toBeInTheDocument();
  });

  it("filters options by search input", async () => {
    const user = userEvent.setup();
    render(<SingleHarness />);

    const trigger = screen.getByText("Select an option").closest("button");
    await user.click(trigger!);

    const search = await screen.findByPlaceholderText("Search...");
    await user.type(search, "gam");

    expect(screen.getByText("Gamma")).toBeInTheDocument();
    expect(screen.queryByText("Alpha")).toBeNull();
    expect(screen.queryByText("Beta")).toBeNull();
  });
});

describe("Combobox (single) unknown values", () => {
  it("renders the raw value as the trigger label when not in options", () => {
    function Harness() {
      const [value, setValue] = useState<string | null>("GO:0016301");
      return (
        <Combobox
          options={[]}
          value={value}
          onChange={setValue}
          placeholder="Type to search..."
        />
      );
    }
    render(<Harness />);
    expect(screen.getByText("GO:0016301")).toBeInTheDocument();
    expect(screen.queryByText("Type to search...")).toBeNull();
  });
});

describe("Combobox (multiple) unknown values", () => {
  it("renders a chip with the raw value when not in options", () => {
    function Harness() {
      const [value, setValue] = useState<string[]>(["GO:0016301"]);
      return (
        <Combobox
          multiple
          options={[]}
          value={value}
          onChange={setValue}
          placeholder="Pick options"
        />
      );
    }
    render(<Harness />);
    expect(screen.getByText("GO:0016301")).toBeInTheDocument();
    expect(screen.getByLabelText("Remove GO:0016301")).toBeInTheDocument();
  });

  it("removes a synthetic chip when the X is clicked", async () => {
    const user = userEvent.setup();
    function Harness() {
      const [value, setValue] = useState<string[]>(["GO:0016301", "GO:0006915"]);
      return (
        <Combobox
          multiple
          options={[]}
          value={value}
          onChange={setValue}
          placeholder="Pick options"
        />
      );
    }
    render(<Harness />);
    expect(screen.getByText("GO:0016301")).toBeInTheDocument();
    expect(screen.getByText("GO:0006915")).toBeInTheDocument();

    await user.click(screen.getByLabelText("Remove GO:0016301"));

    expect(screen.queryByText("GO:0016301")).toBeNull();
    expect(screen.getByText("GO:0006915")).toBeInTheDocument();
  });
});

describe("Combobox (multiple)", () => {
  function MultiHarness() {
    const [value, setValue] = useState<string[]>([]);
    return (
      <Combobox
        multiple
        options={OPTIONS}
        value={value}
        onChange={setValue}
        placeholder="Pick options"
      />
    );
  }

  it("selects multiple values and renders chips", async () => {
    const user = userEvent.setup();
    render(<MultiHarness />);

    const trigger = screen.getByText("Pick options").closest("button");
    await user.click(trigger!);

    await user.click(await screen.findByText("Alpha"));
    await user.click(screen.getByText("Gamma"));

    expect(screen.getAllByText("Alpha")).toHaveLength(2);
    expect(screen.getAllByText("Gamma")).toHaveLength(2);

    const alphaItems = screen.getAllByText("Alpha");
    await user.click(alphaItems[0]!);

    const remaining = screen.queryAllByText("Alpha");
    expect(remaining.length).toBe(1);
  });
});
