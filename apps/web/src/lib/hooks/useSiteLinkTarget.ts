import { useSyncExternalStore } from "react";

import { siteLinkTarget } from "@/lib/utils/siteLinkTarget";

function noSubscription(): () => void {
  return () => {};
}

function browserTarget(): "_top" | "_blank" {
  return siteLinkTarget(window.self, window.top);
}

function serverTarget(): "_blank" {
  return "_blank";
}

/** Where a link to a VEuPathDB site opens in this window. */
export function useSiteLinkTarget(): "_top" | "_blank" {
  return useSyncExternalStore(noSubscription, browserTarget, serverTarget);
}
