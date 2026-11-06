export const TEXT_SCALES = [90, 100, 115, 130] as const;

export type TextScale = (typeof TEXT_SCALES)[number];

export const DEFAULT_TEXT_SCALE: TextScale = 100;

export function applyTextScale(scale: TextScale): void {
  document.documentElement.style.fontSize = `${scale}%`;
}
