import type { ThreadMode } from "@pathfinder/shared/generated/types/ThreadMode";

export const THREAD_MODE_LABELS: Record<ThreadMode, string> = {
  auto: "Auto",
  explore: "Explore",
  build: "Build",
};

export const THREAD_MODE_DESCRIPTIONS: Record<ThreadMode, string> = {
  auto: "PathFinder picks Explore or Build for each message",
  explore:
    "Talk a research question through; nothing is built until you pick a reading",
  build: "Build and change strategies",
};
