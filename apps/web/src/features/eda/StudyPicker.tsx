"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useDebounce } from "use-debounce";
import { toast } from "sonner";
import { siteShortName } from "@pathfinder/shared";
import type { EdaStudyListResponse } from "@pathfinder/shared/generated/types/EdaStudyListResponse";
import type { EdaStudySummaryResponse } from "@pathfinder/shared/generated/types/EdaStudySummaryResponse";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { edaStudySearchOptions, patchConversationEda } from "@/features/eda/api";
import { toUserMessage } from "@/lib/api/errors";
import { useEdaStore } from "@/state/eda";

import { YourDatasets } from "./YourDatasets";

const MIN_QUERY = 2;
const DEBOUNCE_MS = 250;

interface StudyPickerProps {
  siteId: string;
  conversationId: string;
}

export function StudyPicker({ siteId, conversationId }: StudyPickerProps) {
  const [typed, setTyped] = useState("");
  const [query] = useDebounce(typed, DEBOUNCE_MS);
  const search = useQuery({
    ...edaStudySearchOptions(siteId, query),
    meta: { shownInline: true },
  });
  const applyAnalysisState = useEdaStore((s) => s.applyAnalysisState);

  const bind = useMutation({
    mutationFn: (datasetId: string) =>
      patchConversationEda(conversationId, { action: "bind", siteId, datasetId }),
    onSuccess: (response) => {
      if (response.analysis !== null) applyAnalysisState(response.analysis);
    },
    onError: (error) => {
      toast.error(toUserMessage(error, "Could not open the analysis"));
    },
  });

  const trimmed = query.trim();
  return (
    <div data-testid="eda-study-picker" className="mx-auto w-full max-w-2xl">
      <YourDatasets siteId={siteId} onPick={(datasetId) => bind.mutate(datasetId)} />
      <div className="flex items-center gap-2">
        <Input
          data-testid="eda-study-search"
          aria-label="Find a study"
          placeholder="Search studies..."
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
        />
        {search.isFetching ? <Spinner className="size-4" /> : null}
      </div>
      <PickerBody
        siteId={siteId}
        query={trimmed}
        search={search}
        onRetry={() => void search.refetch()}
        onPick={(datasetId) => bind.mutate(datasetId)}
      />
    </div>
  );
}

interface PickerBodyProps {
  siteId: string;
  query: string;
  search: {
    data: EdaStudyListResponse | undefined;
    error: unknown;
  };
  onRetry: () => void;
  onPick: (datasetId: string) => void;
}

function PickerBody({ siteId, query, search, onRetry, onPick }: PickerBodyProps) {
  if (query.length < MIN_QUERY) {
    return (
      <p className="mt-3 text-xs text-muted-foreground">
        Type at least 2 characters to search studies.
      </p>
    );
  }
  if (search.error != null) {
    return (
      <div
        data-testid="eda-study-search-error"
        className="mt-3 text-xs text-destructive"
      >
        <p>{toUserMessage(search.error, "Study search failed")}</p>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="mt-2"
          onClick={onRetry}
        >
          Retry
        </Button>
      </div>
    );
  }
  const studies = search.data === undefined ? [] : search.data.studies;
  if (search.data !== undefined && studies.length === 0) {
    return (
      <p className="mt-3 text-xs text-muted-foreground">
        {`No study on ${siteShortName(siteId)} matches ${query}.`}
      </p>
    );
  }
  return (
    <ul data-testid="eda-study-results" className="mt-3 divide-y divide-border">
      {studies.map((study) => (
        <StudyRow
          key={study.datasetId}
          study={study}
          onPick={() => onPick(study.datasetId)}
        />
      ))}
    </ul>
  );
}

function StudyRow({
  study,
  onPick,
}: {
  study: EdaStudySummaryResponse;
  onPick: () => void;
}) {
  const shortName = study.shortDisplayName;
  const sourceType = study.sourceType;
  const notHere = study.notHere;
  const notHereId = `eda-study-not-here-${study.datasetId}`;
  return (
    <li>
      <button
        type="button"
        data-testid={`eda-study-row-${study.datasetId}`}
        onClick={onPick}
        disabled={notHere !== null}
        aria-describedby={notHere !== null ? notHereId : undefined}
        className="w-full px-2 py-2 text-left hover:bg-accent disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:bg-transparent"
      >
        <span className="block truncate text-sm">{study.displayName}</span>
        <span className="mt-0.5 block text-[11px] text-muted-foreground">
          {shortName !== "" ? <span className="mr-2">{shortName}</span> : null}
          <span className="mr-2 font-mono">{study.datasetId}</span>
          {sourceType !== "" ? <span className="mr-2">{sourceType}</span> : null}
          {study.sites.length > 0 ? (
            <span data-testid={`eda-study-sites-${study.datasetId}`}>
              {study.sites.join(", ")}
            </span>
          ) : null}
        </span>
      </button>
      {notHere !== null ? (
        <p
          id={notHereId}
          data-testid={notHereId}
          className="px-2 pb-2 text-[11px] text-muted-foreground"
        >
          {notHere}
        </p>
      ) : null}
    </li>
  );
}
