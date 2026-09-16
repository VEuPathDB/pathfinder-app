import type { VocabEntry } from "../../utils/paramUtils";

export interface SweepableParam {
  name: string;
  displayName: string;
  kind: "numeric" | "categorical";
  currentValue: string;
  numericValue?: number;
  vocab?: VocabEntry[];
}

export const MAX_CATEGORICAL_CHOICES = 50;

export function truncateLabel(s: string, max: number): string {
  return s.length > max ? s.slice(0, max - 3) + "..." : s;
}
