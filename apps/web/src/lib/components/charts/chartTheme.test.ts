/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from "vitest";

import { buildChartTheme, readChartTokens, CHART_TOKEN_FALLBACKS } from "./chartTheme";
import { UNRESOLVED_SERIES_COLOR } from "./unresolved";
import { DISTINCT_CHART_TOKENS } from "./__fixtures__/chartTokens";

/** The dark ground's chart set, as `globals.css` declares it. */
const DARK_TOKENS: Record<string, string> = {
  "--chart-1": "210 90% 70%",
  "--chart-2": "160 55% 58%",
  "--chart-3": "30 85% 62%",
  "--chart-4": "355 80% 70%",
  "--chart-5": "272 70% 74%",
  "--chart-6": "190 70% 60%",
  "--chart-positive": "160 55% 58%",
  "--chart-negative": "355 80% 70%",
  "--foreground": "210 20% 92%",
  "--muted-foreground": "215 15% 65%",
  "--border": "215 20% 22%",
  "--card": "215 25% 12%",
  "--background": "215 28% 9%",
};

/** The light palette this module used to hardcode. */
const RETIRED_LIGHT_SERIES = "215 70% 50%";

afterEach(() => {
  document.documentElement.removeAttribute("data-theme");
  for (const name of Object.keys(DARK_TOKENS)) {
    document.documentElement.style.removeProperty(name);
  }
});

describe("readChartTokens", () => {
  it("returns the dark values when the document is on the dark ground", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    for (const [name, value] of Object.entries(DARK_TOKENS)) {
      document.documentElement.style.setProperty(name, value);
    }

    const tokens = readChartTokens();

    expect(tokens.series).toEqual([
      "hsl(210, 90%, 70%)",
      "hsl(160, 55%, 58%)",
      "hsl(30, 85%, 62%)",
      "hsl(355, 80%, 70%)",
      "hsl(272, 70%, 74%)",
      "hsl(190, 70%, 60%)",
    ]);
    expect(tokens.positive).toBe("hsl(160, 55%, 58%)");
    expect(tokens.negative).toBe("hsl(355, 80%, 70%)");
    expect(tokens.foreground).toBe("hsl(210, 20%, 92%)");
    expect(tokens.mutedForeground).toBe("hsl(215, 15%, 65%)");
    expect(tokens.border).toBe("hsl(215, 20%, 22%)");
    expect(tokens.card).toBe("hsl(215, 25%, 12%)");
    expect(tokens.background).toBe("hsl(215, 28%, 9%)");
  });

  it("paints the unresolved neutral, not a second copy of the light palette", () => {
    const tokens = readChartTokens();

    expect(tokens.series).toEqual(
      Array.from({ length: 6 }, () => UNRESOLVED_SERIES_COLOR),
    );
    expect(tokens.positive).toBe(UNRESOLVED_SERIES_COLOR);
    expect(tokens.negative).toBe(UNRESOLVED_SERIES_COLOR);
    expect(tokens.series.join(" ")).not.toContain(RETIRED_LIGHT_SERIES);
  });

  it("inherits the surrounding ink for text roles it cannot resolve", () => {
    const tokens = readChartTokens();

    expect(tokens.foreground).toBe("currentColor");
    expect(tokens.mutedForeground).toBe("currentColor");
    expect(tokens.border).toBe("currentColor");
    expect(tokens.card).toBe("transparent");
    expect(tokens.background).toBe("transparent");
  });

  it("names the unresolved set as the fallback set", () => {
    expect(readChartTokens()).toEqual(CHART_TOKEN_FALLBACKS);
  });

  it("wraps a bare HSL triple from the document in hsl()", () => {
    document.documentElement.style.setProperty("--chart-positive", "160 65% 33%");
    const tokens = readChartTokens();
    expect(tokens.positive).toBe("hsl(160, 65%, 33%)");
    document.documentElement.style.removeProperty("--chart-positive");
  });
});

describe("buildChartTheme", () => {
  it("names the six series colors in token order", () => {
    const theme = buildChartTheme(DISTINCT_CHART_TOKENS);
    expect(theme.color).toEqual(DISTINCT_CHART_TOKENS.series);
  });

  it("paints axis text with the muted foreground and gridlines with the border", () => {
    const theme = buildChartTheme(DISTINCT_CHART_TOKENS);
    expect(theme.textStyle.color).toBe(DISTINCT_CHART_TOKENS.foreground);
    expect(theme.valueAxis.axisLabel.color).toBe(DISTINCT_CHART_TOKENS.mutedForeground);
    expect(theme.valueAxis.splitLine.lineStyle.color).toBe(
      DISTINCT_CHART_TOKENS.border,
    );
  });

  it("gives the tooltip the card background and a border", () => {
    const theme = buildChartTheme(DISTINCT_CHART_TOKENS);
    expect(theme.tooltip.backgroundColor).toBe(DISTINCT_CHART_TOKENS.card);
    expect(theme.tooltip.borderColor).toBe(DISTINCT_CHART_TOKENS.border);
  });
});
