import type { TurnFailedPayload } from "@strategist/shared/generated/types/TurnFailedPayload";

import { FailureNotice } from "../FailureNotice";

export function DataTurnFailed({ data }: { data: TurnFailedPayload }) {
  return <FailureNotice detail={data.errorText} />;
}
