"use client";

import { useRouter } from "next/navigation";
import type { EdaAnalysisState } from "@pathfinder/shared";

import { Button } from "@/components/ui/button";
import { Figure } from "@/features/conversation/thread/Figure";
import { useConversationId } from "@/features/conversation/useConversationId";
import { edaTabUrl } from "@/lib/routes";
import { useHydrateEdaPart } from "@/state/eda";

import { useChatHelpers } from "../../runtime/chatHelpersContext";
import { isNewestAnalysisState } from "./analysisStateParts";
import { entityCountCaption } from "./entityCounts";

const MUTED = "text-[11px] text-muted-foreground";

export function DataEdaAnalysisState({ data }: { data: EdaAnalysisState }) {
  useHydrateEdaPart({ kind: "analysis-state", data });
  const conversationId = useConversationId();
  const chat = useChatHelpers();
  const hiddenFilters = data.numFilters - data.filterSummaries.length;
  // The thread keeps one card per analysis: the newest. Older statements
  // yield to it; the plots between them keep their own study captions.
  if (!isNewestAnalysisState(chat.messages, data)) return null;

  return (
    <Figure
      testId="data-eda-analysis-state"
      title={data.studyDisplayName.length > 0 ? data.studyDisplayName : data.datasetId}
      caption={entityCountCaption(data.entityCounts)}
      action={
        conversationId !== null ? (
          <OpenEdaTab siteId={data.siteId} conversationId={conversationId} />
        ) : null
      }
    >
      <div className="text-xs">
        <div className={`min-w-0 ${MUTED}`}>{data.displayName}</div>

        {data.filterSummaries.length > 0 ? (
          <div className="mt-2 flex flex-wrap gap-1">
            {data.filterSummaries.map((summary, index) => (
              <span
                key={index}
                data-testid={`data-eda-filter-chip-${String(index)}`}
                className="rounded-full bg-muted/50 px-2 py-0.5 text-[11px]"
              >
                {summary}
              </span>
            ))}
          </div>
        ) : (
          <div className={`mt-2 ${MUTED}`}>No filters yet</div>
        )}
        {hiddenFilters > 0 ? (
          <div data-testid="data-eda-filter-overflow" className={`mt-1 ${MUTED}`}>
            {`${hiddenFilters.toLocaleString()} more ${hiddenFilters === 1 ? "filter" : "filters"}`}
          </div>
        ) : null}

        <div className={`mt-2 ${MUTED}`}>
          {`${data.numComputations.toLocaleString()} ${data.numComputations === 1 ? "computation" : "computations"}`}
        </div>
      </div>
    </Figure>
  );
}

function OpenEdaTab({
  siteId,
  conversationId,
}: {
  siteId: string;
  conversationId: string;
}) {
  const router = useRouter();
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className="h-7 shrink-0 px-2 text-xs"
      onClick={() => router.push(edaTabUrl(siteId, conversationId))}
    >
      Open study
    </Button>
  );
}
