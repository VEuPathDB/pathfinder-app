import { z } from "zod";

const offset = z.number().int().min(0);
const anchor = z.enum(["start", "stop"]);
const direction = z.enum(["+", "-"]);
const region = z.enum(["exact", "upstream", "downstream", "custom"]);

export const colocationSchema = z.object({
  operation: z.enum(["overlaps", "contains", "is contained in"]),
  strand: z.enum(["either strand", "same strand", "opposite strand"]),
  output: z.enum(["a", "b"]),
  regionA: region,
  beginA: anchor,
  beginDirectionA: direction,
  beginOffsetA: offset,
  endA: anchor,
  endDirectionA: direction,
  endOffsetA: offset,
  regionB: region,
  beginB: anchor,
  beginDirectionB: direction,
  beginOffsetB: offset,
  endB: anchor,
  endDirectionB: direction,
  endOffsetB: offset,
});

export type ColocationFormValues = z.infer<typeof colocationSchema>;

export const DEFAULT_COLOCATION: ColocationFormValues = {
  operation: "overlaps",
  strand: "either strand",
  output: "a",
  regionA: "exact",
  beginA: "start",
  beginDirectionA: "+",
  beginOffsetA: 0,
  endA: "stop",
  endDirectionA: "+",
  endOffsetA: 0,
  regionB: "exact",
  beginB: "start",
  beginDirectionB: "+",
  beginOffsetB: 0,
  endB: "stop",
  endDirectionB: "+",
  endOffsetB: 0,
};
