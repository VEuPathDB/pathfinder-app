"use client";

import { useIsomorphicLayoutEffect } from "usehooks-ts";

import { useAddressPath } from "@/app/hooks/useAddressPath";
import { reportLocation } from "@/lib/frameBridge";

export function FrameLocationReporter() {
  const path = useAddressPath();
  useIsomorphicLayoutEffect(() => reportLocation(window, path), [path]);
  return null;
}
