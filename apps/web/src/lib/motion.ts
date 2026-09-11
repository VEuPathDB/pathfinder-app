"use client";

import { useSyncExternalStore } from "react";
import type { MotionProps } from "motion/react";

const REDUCE_QUERY = "(prefers-reduced-motion: reduce)";

function subscribe(onChange: () => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  const query = window.matchMedia(REDUCE_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function getSnapshot(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia(REDUCE_QUERY).matches;
}

function getServerSnapshot(): boolean {
  return false;
}

/** True when the viewer asks for reduced motion. */
export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

/** The props that carry a motion element from an entrance to its settled
 *  state. `animate` holds that settled state and stays on the element. */
export interface EntranceProps {
  initial: NonNullable<MotionProps["initial"]>;
  exit?: NonNullable<MotionProps["exit"]>;
  transition: NonNullable<MotionProps["transition"]>;
}

/** Under reduced motion the element paints at its `animate` values from the
 *  first frame and every entrance and exit runs at zero duration. A `motion`
 *  animation is JavaScript, so the CSS rules for the preference miss it. */
export function useEntrance(props: EntranceProps): EntranceProps {
  return usePrefersReducedMotion()
    ? { ...props, initial: false, transition: { duration: 0 } }
    : props;
}
