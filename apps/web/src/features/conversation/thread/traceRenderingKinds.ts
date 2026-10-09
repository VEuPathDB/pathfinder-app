import { dataPartComponents } from "../content/contentComponents";
import { noRender } from "../content/coreDataParts";

/**
 * Kinds that draw but are not figures a run produced: three turn-level notices
 * and the durable job, which the trace draws as a task row.
 */
const NOT_A_FIGURE: ReadonlySet<string> = new Set([
  "data-turn-failed",
  "data-turn-stopped",
  "data-turn-withdrawn",
  "data-background-task-started",
]);

let derived: ReadonlySet<string> | null = null;

/**
 * The kinds a run hoists as figures, read from the renderer map by identity so
 * a kind that starts or stops drawing joins or leaves the set on its own. The
 * map is read on first call: the registry imports the anchor that asks for it.
 */
export function traceRenderingKinds(): ReadonlySet<string> {
  derived ??= new Set(
    Object.entries(dataPartComponents)
      .filter(([kind, component]) => component !== noRender && !NOT_A_FIGURE.has(kind))
      .map(([kind]) => kind),
  );
  return derived;
}
