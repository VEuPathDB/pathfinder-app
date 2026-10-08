/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { fireEvent, render } from "@testing-library/react";

import { SiteIcon } from "./SiteIcon";

function iconImage(container: HTMLElement): HTMLImageElement {
  const image = container.querySelector("img");
  if (image === null) throw new Error("the site icon renders no image");
  return image;
}

describe("SiteIcon", () => {
  it("loads the site's icon from under the base path", () => {
    const { container } = render(<SiteIcon siteId="PlasmoDB" />);

    const src = iconImage(container).getAttribute("src") ?? "";
    expect(new URL(src, "http://localhost").searchParams.get("url")).toBe(
      "/pathfinder/icons/plasmodb.png",
    );
  });

  it("falls back to the portal icon under the base path when the icon fails", () => {
    const { container } = render(<SiteIcon siteId="notasite" />);
    const image = iconImage(container);

    fireEvent.error(image);

    expect(image.getAttribute("src")).toBe("/pathfinder/icons/veupathdb.png");
  });
});
