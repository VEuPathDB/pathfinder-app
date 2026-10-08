"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useIsomorphicLayoutEffect } from "usehooks-ts";

import { reportLocation } from "@/lib/frameBridge";

export function FrameLocationReporter() {
  const pathname = usePathname();
  const search = useSearchParams().toString();
  const path = search ? `${pathname}?${search}` : pathname;
  useIsomorphicLayoutEffect(() => reportLocation(window, path), [path]);
  return null;
}
