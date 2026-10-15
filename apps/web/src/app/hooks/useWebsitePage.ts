"use client";

import { useIsomorphicLayoutEffect } from "usehooks-ts";

import { useAddressPath } from "@/app/hooks/useAddressPath";
import { goToWebsitePage } from "@/lib/frameBridge";

export function useWebsitePage(sitePageUrl: string): void {
  const path = useAddressPath();
  useIsomorphicLayoutEffect(
    () => goToWebsitePage(window, sitePageUrl, path),
    [sitePageUrl, path],
  );
}
