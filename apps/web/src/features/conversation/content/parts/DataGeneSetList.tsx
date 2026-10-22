import {
  siteShortName,
  type ListedGeneSet,
  type ListedGeneSets,
} from "@pathfinder/shared";

import { Figure } from "@/features/conversation/thread/Figure";

import { SavedOnIcon } from "./SavedOnIcon";

type OutOfDate = NonNullable<ListedGeneSet["outOfDate"]>;

function nouns(set: ListedGeneSet): string {
  return `${set.recordNoun ?? "gene"}s`;
}

function countHere(set: ListedGeneSet, siteId: string): string {
  if (set.savedOn === siteId && set.genesHere === set.geneCount) {
    return `${set.geneCount.toLocaleString()} ${nouns(set)}`;
  }
  return `${set.genesHere.toLocaleString()} of ${set.geneCount.toLocaleString()} ${nouns(set)} here`;
}

function outOfDate(reason: OutOfDate, noun: string): string {
  switch (reason.kind) {
    case "above_the_cap":
      return `Out of date: the strategy now returns ${reason.count.toLocaleString()} ${noun}, more than the ${reason.cap.toLocaleString()} a gene set holds`;
    case "not_genes":
      return `Out of date: the strategy now returns ${reason.recordClass === "" ? "unnamed" : reason.recordClass} records, which are not genes`;
    case "no_genes":
      return "Out of date: the strategy now returns no genes";
    default: {
      const unknown: never = reason;
      return unknown;
    }
  }
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
            <li key={set.id} className="min-w-0">
              <div className="flex min-w-0 items-center gap-2">
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
              </div>
              {set.outOfDate == null ? null : (
                <div data-testid="gene-set-out-of-date" className="text-warning">
                  {outOfDate(set.outOfDate, nouns(set))}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Figure>
  );
}
