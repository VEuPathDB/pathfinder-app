/** The bare "H S% L%" triple a color custom property holds. */
export function hslTriple(h: number, s: number, l: number): string {
  return `${String(h)} ${String(s)}% ${String(l)}%`;
}

/** A bare triple does not paint on its own; this wraps one so it does. */
export function hslFromTriple(triple: string): string {
  return `hsl(${triple.trim().split(/\s+/).join(", ")})`;
}
