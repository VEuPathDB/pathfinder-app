import {
  findingViewCertaintyEnum,
  findingViewCheckEnum,
  findingViewErrorTypeEnum,
  type FindingViewCertaintyEnumKey,
  type FindingViewCheckEnumKey,
  type FindingViewErrorTypeEnumKey,
} from "@pathfinder/shared/generated/types/FindingView";
import type { ListAuditFindingsQueryParams } from "@pathfinder/shared/generated/types/ListAuditFindings";

export const ORIGINS = ["sample", "unsampled", "target"] as const;
export type Origin = (typeof ORIGINS)[number];
export const FINDINGS_PAGE = 50;

export interface FindingFilterState {
  check: FindingViewCheckEnumKey | null;
  screenedGenome: string | null;
  genome: string | null;
  errorType: FindingViewErrorTypeEnumKey | null;
  certainty: FindingViewCertaintyEnumKey | null;
  origin: Origin | null;
  offset: number;
}

const ORIGIN_QUERY: Record<
  Origin,
  Pick<ListAuditFindingsQueryParams, "sampled" | "target">
> = {
  sample: { sampled: true, target: false },
  unsampled: { sampled: false },
  target: { target: true },
};

export function oneOf<T extends string>(
  values: readonly T[],
  raw: string | null,
): T | null {
  return values.find((value) => value === raw) ?? null;
}

export function filtersFromSearch(search: URLSearchParams): FindingFilterState {
  const offset = Number(search.get("offset") ?? "0");
  return {
    check: oneOf(Object.values(findingViewCheckEnum), search.get("check")),
    screenedGenome: search.get("screenedGenome"),
    genome: search.get("genome"),
    errorType: oneOf(Object.values(findingViewErrorTypeEnum), search.get("errorType")),
    certainty: oneOf(Object.values(findingViewCertaintyEnum), search.get("certainty")),
    origin: oneOf(ORIGINS, search.get("origin")),
    offset: Number.isInteger(offset) && offset > 0 ? offset : 0,
  };
}

export function searchFromFilters(state: FindingFilterState): string {
  const search = new URLSearchParams();
  const named: readonly (readonly [string, string | null])[] = [
    ["check", state.check],
    ["screenedGenome", state.screenedGenome],
    ["genome", state.genome],
    ["errorType", state.errorType],
    ["certainty", state.certainty],
    ["origin", state.origin],
  ];
  for (const [key, value] of named) if (value !== null) search.set(key, value);
  if (state.offset > 0) search.set("offset", String(state.offset));
  const text = search.toString();
  return text === "" ? "" : `?${text}`;
}

export function findingQuery(state: FindingFilterState): ListAuditFindingsQueryParams {
  return {
    ...(state.check === null ? {} : { check: state.check }),
    ...(state.screenedGenome === null ? {} : { screenedGenome: state.screenedGenome }),
    ...(state.genome === null ? {} : { genome: state.genome }),
    ...(state.errorType === null ? {} : { errorType: state.errorType }),
    ...(state.certainty === null ? {} : { certainty: state.certainty }),
    ...(state.origin === null ? {} : ORIGIN_QUERY[state.origin]),
    offset: state.offset,
    limit: FINDINGS_PAGE,
  };
}
