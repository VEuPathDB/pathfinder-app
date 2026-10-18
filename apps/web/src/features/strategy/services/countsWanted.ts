export function countsWanted({
  steps,
  savesInFlight,
}: {
  steps: readonly { estimatedSize?: number | null }[];
  savesInFlight: number;
}): boolean {
  if (savesInFlight > 0) return false;
  return steps.some((step) => typeof step.estimatedSize !== "number");
}
