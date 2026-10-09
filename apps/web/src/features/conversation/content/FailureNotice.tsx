import { ActionBarPrimitive } from "@assistant-ui/react";
import { AlertTriangle, RefreshCw } from "lucide-react";

/** The failure notice, shown live from the error chunk and after a reload from
 * the `data-turn-failed` or `data-turn-withdrawn` part. */
export function FailureNotice({
  detail,
  heading = "Response failed",
  retry = true,
}: {
  detail: string;
  heading?: string;
  retry?: boolean;
}) {
  return (
    <div
      data-testid="failure-notice"
      className="flex items-start gap-3 text-sm text-destructive"
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-medium">{heading}</p>
        <p className="mt-0.5 break-words text-xs text-destructive">{detail}</p>
        {retry && (
          <ActionBarPrimitive.Reload asChild>
            <button
              type="button"
              className="mt-2 inline-flex items-center gap-1.5 px-0 py-1 text-xs font-medium text-destructive underline-offset-2 transition-colors hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-destructive"
            >
              <RefreshCw className="size-3" aria-hidden />
              Try again
            </button>
          </ActionBarPrimitive.Reload>
        )}
      </div>
    </div>
  );
}
