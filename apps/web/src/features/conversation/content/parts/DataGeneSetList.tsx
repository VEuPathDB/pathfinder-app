import {
  siteShortName,
  type ListedGeneSet,
  type ListedGeneSets,
} from "@pathfinder/shared";

import { Figure } from "@/features/conversation/thread/Figure";

import { SavedOnIcon } from "./SavedOnIcon";

function countHere(set: ListedGeneSet, siteId: string): string {
  if (set.savedOn === siteId && set.genesHere === set.geneCount) {
    return `${set.geneCount.toLocaleString()} genes`;
  }
  return `${set.genesHere.toLocaleString()} of ${set.geneCount.toLocaleString()} genes here`;
}

function caption({ siteId, geneSets }: ListedGeneSets): string {
  const site = siteShortName(siteId);
  if (geneSets.length === 0) return `No saved gene set has genes on ${site}`;
  const sets = geneSets.length === 1 ? "gene set" : "gene sets";
  return `${geneSets.length.toLocaleString()} ${sets} with genes on ${site}`;
}

export function DataGeneSetList({ data }: { data: ListedGeneSets }) {
  return (
    <Figure testId="data-gene-set-list" title="Saved gene sets" caption={caption(data)}>
      {data.geneSets.length === 0 ? null : (
        <ul className="space-y-0.5 text-xs">
          {data.geneSets.map((set) => (
            <li key={set.id} className="flex min-w-0 items-center gap-2">
              <SavedOnIcon siteId={set.savedOn} />
              <span className="min-w-0 truncate" title={set.name}>
                {set.name}
              </span>
              {set.savedHere ? (
                <span className="shrink-0 rounded bg-muted px-1 py-0.5 text-[10px]">
                  This conversation
                </span>
              ) : null}
              <span className="ml-auto shrink-0 tabular-nums text-muted-foreground">
                {countHere(set, data.siteId)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Figure>
  );
}
