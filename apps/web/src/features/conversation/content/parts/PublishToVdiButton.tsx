"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { GeneSet, VdiPublicationStatus, VdiVisibility } from "@pathfinder/shared";
import { ExternalLink, Share2 } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { toUserMessage } from "@/lib/api/errors";
import { getGeneSetVdiPublication, publishGeneSetToVdi } from "@/lib/api/geneSets";
import { queryKeyPrefixes } from "@/lib/query/keys";

const VISIBILITIES: readonly VdiVisibility[] = ["private", "protected", "public"];
const STATUS_POLL_MS = 5000;
const PILL =
  "flex items-center gap-1 rounded-full border border-border px-2 py-0.5" +
  " text-[10px] font-medium text-muted-foreground hover:text-foreground" +
  " disabled:opacity-50";

type PublishState =
  | { kind: "idle" }
  | { kind: "confirming" }
  | { kind: "publishing" }
  | { kind: "published"; vdiId: string }
  | { kind: "failed"; message: string };

function readVisibility(value: string): VdiVisibility {
  return VISIBILITIES.find((option) => option === value) ?? "private";
}

function statusLine(status: VdiPublicationStatus | undefined): string {
  if (status === undefined) return "Reading publication status...";
  if (status.installed) return `Installed on ${status.installedTargets.join(", ")}`;
  if (status.isTerminal) return "The site could not install this dataset";
  if (status.upload !== "success") return "Uploading to the site...";
  if (status.importStatus === "in-progress")
    return "The site is importing the dataset...";
  if (status.importStatus === "complete")
    return "Imported; the site is installing it...";
  return "Uploaded; the site imports it next";
}

function PublishedLine({ geneSetId }: { geneSetId: string }) {
  const status = useQuery({
    queryKey: [...queryKeyPrefixes.geneSets, "vdi-publication", geneSetId] as const,
    queryFn: () => getGeneSetVdiPublication(geneSetId),
    refetchInterval: (query) =>
      query.state.status === "error" || query.state.data?.isTerminal === true
        ? false
        : STATUS_POLL_MS,
    meta: { shownInline: true },
  });

  if (status.data === undefined && status.error !== null) {
    return (
      <span role="alert" className="text-[10px] text-destructive">
        {toUserMessage(status.error, "The publication status could not be read.")}
      </span>
    );
  }

  return (
    <span className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
      <Share2 className="size-3" aria-hidden />
      <span>{statusLine(status.data)}</span>
      {status.data != null && (
        <a
          className="flex items-center gap-0.5 underline hover:text-foreground"
          href={status.data.datasetUrl}
          rel="noreferrer"
          target="_blank"
        >
          Open dataset
          <ExternalLink className="size-2.5" aria-hidden />
        </a>
      )}
    </span>
  );
}

/**
 * Publishes a gene set as a VEuPathDB user dataset.
 *
 * The dataset outlives the conversation and is visible in the site's own
 * workspace, so the action asks for confirmation before it runs.
 */
export function PublishToVdiButton({ geneSet }: { geneSet: GeneSet }) {
  const [state, setState] = useState<PublishState>({ kind: "idle" });
  const [visibility, setVisibility] = useState<VdiVisibility>("private");
  const queryClient = useQueryClient();
  const visibilityId = useId();

  const publishedId =
    state.kind === "published" ? state.vdiId : (geneSet.vdiId ?? null);
  if (publishedId != null && publishedId !== "") {
    return <PublishedLine geneSetId={geneSet.id} />;
  }

  const publish = async (): Promise<void> => {
    setState({ kind: "publishing" });
    try {
      const published = await publishGeneSetToVdi(geneSet.id, {
        name: geneSet.name,
        visibility,
      });
      setState({ kind: "published", vdiId: published.vdiId });
      void queryClient.invalidateQueries({ queryKey: queryKeyPrefixes.geneSets });
      toast.success(`Published ${published.geneCount.toLocaleString()} genes`);
    } catch (err) {
      setState({ kind: "failed", message: toUserMessage(err, "Publish failed") });
    }
  };

  if (state.kind === "idle" || state.kind === "failed") {
    return (
      <span className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => setState({ kind: "confirming" })}
          disabled={geneSet.geneCount === 0}
          title="Publish these genes as a user dataset on this VEuPathDB site"
          className={PILL}
        >
          <Share2 className="size-3" aria-hidden />
          Publish to VEuPathDB workspace
        </button>
        {state.kind === "failed" && (
          <span role="alert" className="text-[10px] text-destructive">
            {state.message}
          </span>
        )}
      </span>
    );
  }

  return (
    <span className="flex items-center gap-1.5">
      <label className="text-[10px] text-muted-foreground" htmlFor={visibilityId}>
        Visibility
      </label>
      <select
        id={visibilityId}
        value={visibility}
        disabled={state.kind === "publishing"}
        onChange={(e) => setVisibility(readVisibility(e.target.value))}
        className="rounded border border-border bg-background px-1 py-0.5 text-[10px]"
      >
        {VISIBILITIES.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      <button
        type="button"
        onClick={() => void publish()}
        disabled={state.kind === "publishing"}
        className={PILL}
      >
        {state.kind === "publishing" ? "Publishing..." : "Confirm publish"}
      </button>
      <button
        type="button"
        onClick={() => setState({ kind: "idle" })}
        disabled={state.kind === "publishing"}
        className={PILL}
      >
        Cancel
      </button>
    </span>
  );
}
