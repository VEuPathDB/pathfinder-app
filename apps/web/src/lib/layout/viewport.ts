/** The width a side panel needs before it may take space from the thread. */
export const SIDE_PANEL_MIN_WIDTH_PX = 900;

/** Whether the window is too narrow to hold a side panel beside the thread. */
export function viewportIsNarrow(): boolean {
  return typeof window !== "undefined" && window.innerWidth < SIDE_PANEL_MIN_WIDTH_PX;
}
