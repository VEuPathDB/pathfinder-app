export const NAV_RAIL_WIDTH_PX = 44;
export const SIDEBAR_SEPARATOR_PX = 4;
export const MIN_CHAT_WIDTH_PX = 600;
export const SIDEBAR_WIDTH_PX = 360;
export const RIGHT_PANEL_WIDTH_PX = 360;

export type Side = "left" | "right";

export interface DockInput {
  viewport: number;
  leftOpen: boolean;
  leftWidth: number;
  rightOpen: boolean;
  rightWidth: number;
  lastOpened: Side | null;
}

export interface DockLayout {
  leftFloats: boolean;
  rightFloats: boolean;
}

function chatWidth(input: DockInput, left: boolean, right: boolean): number {
  return (
    input.viewport -
    NAV_RAIL_WIDTH_PX -
    (left ? input.leftWidth + SIDEBAR_SEPARATOR_PX : 0) -
    (right ? input.rightWidth : 0)
  );
}

export function dockLayout(input: DockInput): DockLayout {
  const { leftOpen, rightOpen } = input;
  if (chatWidth(input, leftOpen, rightOpen) >= MIN_CHAT_WIDTH_PX) {
    return { leftFloats: false, rightFloats: false };
  }
  if (leftOpen && rightOpen) {
    const leftFirst = input.lastOpened === "left";
    const keptFits = leftFirst
      ? chatWidth(input, false, true) >= MIN_CHAT_WIDTH_PX
      : chatWidth(input, true, false) >= MIN_CHAT_WIDTH_PX;
    return leftFirst
      ? { leftFloats: true, rightFloats: !keptFits }
      : { leftFloats: !keptFits, rightFloats: true };
  }
  return { leftFloats: leftOpen, rightFloats: rightOpen };
}
