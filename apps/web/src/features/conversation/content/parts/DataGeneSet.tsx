"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { GeneSet, GeneSetPart } from "@pathfinder/shared";
import { useState } from "react";

import { Figure } from "@/features/conversation/thread/Figure";
import { geneSetsListOptions } from "@/lib/api/geneSets";
import { queryKeyPrefixes } from "@/lib/query/keys";

import { DeleteGeneSetButton } from "./DeleteGeneSetButton";
import { PublishToVdiButton } from "./PublishToVdiButton";

/** The set as the researcher's list holds it now: the set, "deleted" when the
 * list no longer carries it, or null while the list is unread. */
function useHeldSet(data: GeneSetPart): GeneSet | "deleted" | null {
  const list = useQuery(geneSetsListOptions(data.siteId));
  if (list.data === undefined) return null;
  return list.data.find((set) => set.id === data.geneSetId) ?? "deleted";
}

export function DataGeneSet({ data }: { data: GeneSetPart }) {
  const queryClient = useQueryClient();
  const [deletedHere, setDeletedHere] = useState(false);
  const held = useHeldSet(data);
  const deleted = deletedHere || held === "deleted";
  const actionable = deleted || held === null ? null : held;
  const onDeleted = () => {
    setDeletedHere(true);
    void queryClient.invalidateQueries({ queryKey: queryKeyPrefixes.geneSets });
  };

  return (
    <Figure
      testId="data-gene-set"
      title={data.name}
      caption={`${data.geneCount.toLocaleString()} genes on ${data.siteId}`}
    >
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span
          className={`inline-block size-1.5 rounded-full ${deleted ? "bg-muted-foreground" : "bg-success"}`}
        />
        <span>{deleted ? "Gene set deleted" : "Gene set created"}</span>
        {actionable !== null ? (
          <>
            <PublishToVdiButton geneSet={actionable} />
            <DeleteGeneSetButton
              geneSetId={data.geneSetId}
              name={data.name}
              onDeleted={onDeleted}
            />
          </>
        ) : null}
      </div>
    </Figure>
  );
}
