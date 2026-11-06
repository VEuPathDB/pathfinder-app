export const THREAD_MODES = ["auto", "explore", "build"] as const;

export type ThreadMode = (typeof THREAD_MODES)[number];

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

const NEXT_THREAD_MODE: Record<ThreadMode, ThreadMode> = {
  auto: "explore",
  explore: "build",
  build: "auto",
};

export function nextThreadMode(mode: ThreadMode): ThreadMode {
  return NEXT_THREAD_MODE[mode];
}
