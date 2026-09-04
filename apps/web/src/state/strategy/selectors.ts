import type { Step, Strategy } from "@pathfinder/shared";

const EMPTY_STEPS_BY_ID: Record<string, Step> = Object.freeze({});

export function stepsById(strategy: Strategy | null | undefined): Record<string, Step> {
  const steps = strategy?.steps;
  if (!steps || steps.length === 0) return EMPTY_STEPS_BY_ID;
  return getCachedStepsById(steps);
}

const STEPS_CACHE = new WeakMap<readonly Step[], Record<string, Step>>();

function getCachedStepsById(steps: readonly Step[]): Record<string, Step> {
  const cached = STEPS_CACHE.get(steps);
  if (cached) return cached;
  const map: Record<string, Step> = {};
  for (const s of steps) {
    map[s.id] = s;
  }
  STEPS_CACHE.set(steps, map);
  return map;
}
