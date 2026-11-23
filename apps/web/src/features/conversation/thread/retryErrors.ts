import { z } from "zod";

const validationErrorsSchema = z
  .array(
    z.object({
      loc: z.array(z.union([z.string(), z.number()])),
      msg: z.string(),
    }),
  )
  .nonempty();

function parsedJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export function retryErrorLine(errorText: string): string {
  const parsed = validationErrorsSchema.safeParse(parsedJson(errorText));
  if (!parsed.success) return errorText;
  const errors = parsed.data;
  const noun = errors.length === 1 ? "validation error" : "validation errors";
  const said = errors.map(({ loc, msg }) =>
    loc.length === 0 ? msg : `${loc.join(".")}: ${msg}`,
  );
  return `${errors.length} ${noun}: ${said.join("; ")}`;
}
