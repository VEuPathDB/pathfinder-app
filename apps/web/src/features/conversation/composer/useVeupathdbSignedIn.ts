"use client";

import { useQuery } from "@tanstack/react-query";

import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { useSessionStore } from "@/state/useSessionStore";

export const SIGN_IN_TO_BUILD = "Sign in to VEuPathDB to build strategies";

/** True only when VEuPathDB reports a registered login for the current site. */
export function useVeupathdbSignedIn(): boolean {
  const siteId = useSessionStore((s) => s.selectedSite);
  const { data } = useQuery(authStatusOptions(siteId));
  return data?.signedIn === true;
}
