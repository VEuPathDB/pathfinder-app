"use client";

import { useQuery } from "@tanstack/react-query";
import { siteShortName } from "@pathfinder/shared";
import type { EdaOwnDatasetResponse } from "@pathfinder/shared/generated/types/EdaOwnDatasetResponse";

import { Button } from "@/components/ui/button";
import { ownDatasetsOptions } from "@/features/eda/api";
import { toUserMessage } from "@/lib/api/errors";

const STATE_TEXT: Record<EdaOwnDatasetResponse["state"], string> = {
  installing: "Installing on VEuPathDB",
  waiting: "Installed; the study is not visible yet.",
  installed: "Your upload",
  failed: "The install failed",
};

interface YourDatasetsProps {
  siteId: string;
  onPick: (datasetId: string) => void;
}

/** The researcher's own uploads on this site, and the site's page for new ones. */
export function YourDatasets({ siteId, onPick }: YourDatasetsProps) {
  const datasets = useQuery({
    ...ownDatasetsOptions(siteId),
    meta: { shownInline: true },
  });
  const rows = datasets.data?.datasets ?? [];
  return (
    <section data-testid="eda-your-datasets" className="mb-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-medium">Your datasets</h3>
        {datasets.data !== undefined ? (
          <Button asChild size="sm" variant="outline">
            <a href={datasets.data.uploadUrl} target="_blank" rel="noopener noreferrer">
              Upload on VEuPathDB
            </a>
          </Button>
        ) : null}
      </div>
      {datasets.error != null ? (
        <p className="mt-2 text-xs text-destructive">
          {toUserMessage(datasets.error, "Could not read your datasets")}
        </p>
      ) : null}
      <ul className="mt-2 divide-y divide-border">
        {rows.map((dataset) => (
          <OwnDatasetRow key={dataset.vdiId} dataset={dataset} onPick={onPick} />
        ))}
      </ul>
      {datasets.data !== undefined && rows.length === 0 ? (
        <p className="mt-2 text-xs text-muted-foreground">
          {`No datasets of yours on ${siteShortName(siteId)}.`}
        </p>
      ) : null}
    </section>
  );
}

function OwnDatasetRow({
  dataset,
  onPick,
}: {
  dataset: EdaOwnDatasetResponse;
  onPick: (datasetId: string) => void;
}) {
  const datasetId = dataset.state === "installed" ? dataset.datasetId : null;
  const tone =
    dataset.state === "failed" ? "text-destructive" : "text-muted-foreground";
  const detail = (
    <>
      <span className="block truncate text-sm">{dataset.name}</span>
      <span className={`mt-0.5 block text-[11px] ${tone}`}>
        {dataset.message ?? STATE_TEXT[dataset.state]}
      </span>
    </>
  );
  return (
    <li data-testid={`eda-own-dataset-${dataset.vdiId}`}>
      {datasetId !== null ? (
        <button
          type="button"
          onClick={() => onPick(datasetId)}
          className="w-full px-2 py-2 text-left hover:bg-accent"
        >
          {detail}
        </button>
      ) : (
        <div className="px-2 py-2">{detail}</div>
      )}
    </li>
  );
}
