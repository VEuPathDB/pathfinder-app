import { recordEvent } from "@pathfinder/shared/generated/hooks/useRecordEvent";
import type { RecordEventMutationRequest } from "@pathfinder/shared/generated/types/RecordEvent";

/** Report one product event. A failed report is logged and never reaches the UI. */
export function recordProductEvent(event: RecordEventMutationRequest): void {
  recordEvent(event).catch((err: unknown) => {
    console.warn(`recordProductEvent(${event.event}) failed`, err);
  });
}
