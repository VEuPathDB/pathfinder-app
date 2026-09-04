export interface VennInput {
  key: string;
  geneIds: string[];
}

interface VennDatum {
  key: string[];
  data: number;
}

/**
 * Convert N gene sets into reaviz VennDiagram data format.
 * Returns inclusive intersection counts for every non-empty subset.
 */
export function computeVennData(sets: VennInput[]): VennDatum[] {
  const n = sets.length;
  const lookups = sets.map((s) => new Set(s.geneIds));
  const result: VennDatum[] = [];

  for (let mask = 1; mask < 1 << n; mask++) {
    const subsetKeys: string[] = [];
    const subsetIndices: number[] = [];
    for (let i = 0; i < n; i++) {
      if (mask & (1 << i)) {
        const set = sets[i];
        if (set != null) subsetKeys.push(set.key);
        subsetIndices.push(i);
      }
    }

    // Count genes present in ALL sets in this subset
    // Use the smallest set in the subset as the candidate pool
    const firstIdx = subsetIndices[0];
    if (firstIdx == null) continue;
    let smallestIdx = firstIdx;
    for (const idx of subsetIndices) {
      const currentSet = sets[idx];
      const smallestSet = sets[smallestIdx];
      if (
        currentSet != null &&
        smallestSet != null &&
        currentSet.geneIds.length < smallestSet.geneIds.length
      ) {
        smallestIdx = idx;
      }
    }

    const smallestSet = sets[smallestIdx];
    if (smallestSet == null) continue;
    let count = 0;
    for (const gene of smallestSet.geneIds) {
      let inAll = true;
      for (const idx of subsetIndices) {
        if (idx !== smallestIdx && lookups[idx]?.has(gene) !== true) {
          inAll = false;
          break;
        }
      }
      if (inAll) count++;
    }

    result.push({ key: subsetKeys, data: count });
  }

  return result;
}

/**
 * Apply log scaling to Venn data so extremely large sets don't
 * make small sets invisible. Preserves zeros, ordering, and keys.
 * Use this for display sizing only — real counts stay in labels.
 */
export function logScaleVennData(data: VennDatum[]): VennDatum[] {
  return data.map((d) => ({
    key: d.key,
    data: d.data > 0 ? Math.log(d.data + 1) : 0,
  }));
}

/**
 * Compute exclusive gene IDs for each Venn region.
 * A gene belongs to the region keyed by EXACTLY the sets it's in.
 */
export function computeExclusiveRegions(sets: VennInput[]): Map<string, string[]> {
  const n = sets.length;
  const lookups = sets.map((s) => new Set(s.geneIds));
  const allGenes = new Set(sets.flatMap((s) => s.geneIds));
  const regions = new Map<string, string[]>();

  for (const gene of allGenes) {
    const memberKeys: string[] = [];
    for (let i = 0; i < n; i++) {
      if (lookups[i]?.has(gene) === true) memberKeys.push(sets[i]?.key ?? "");
    }
    const regionKey = memberKeys.join(",");
    const list = regions.get(regionKey);
    if (list) {
      list.push(gene);
    } else {
      regions.set(regionKey, [gene]);
    }
  }

  return regions;
}
