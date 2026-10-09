import type { TurnWithdrawnPayload } from "@pathfinder/shared/generated/types/TurnWithdrawnPayload";

import { FailureNotice } from "../FailureNotice";

export function DataTurnWithdrawn({ data }: { data: TurnWithdrawnPayload }) {
  return (
    <FailureNotice heading="Request declined" detail={data.errorText} retry={false} />
  );
}
