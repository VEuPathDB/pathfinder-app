import { History } from "lucide-react";

/** Stands in for a part that an earlier version logged in a shape this
 * version does not read. */
export function StalePartNotice({ subject }: { subject: string }) {
  return (
    <div
      data-testid="stale-part-notice"
      className="flex items-center gap-2 text-xs text-muted-foreground"
    >
      <History className="size-3.5 shrink-0" aria-hidden />
      <span>{`${subject} from an earlier version of PathFinder can't be shown.`}</span>
    </div>
  );
}
