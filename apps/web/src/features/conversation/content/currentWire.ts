import type { z } from "zod";

/** True when a logged payload has the shape the current wire carries. The
 * payload keeps its identity, so a reader that compares parts still finds it. */
export function isCurrentWire<T>(schema: z.ZodType<T>, data: unknown): data is T {
  return schema.safeParse(data).success;
}
