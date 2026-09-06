import { queryOptions } from "@tanstack/react-query";
import { attributesResponseSchema } from "@pathfinder/shared/generated/zod/attributesResponseSchema";
import { distributionResponseSchema } from "@pathfinder/shared/generated/zod/distributionResponseSchema";
import { recordDetailResponseSchema } from "@pathfinder/shared/generated/zod/recordDetailResponseSchema";
import { recordsResponseSchema } from "@pathfinder/shared/generated/zod/recordsResponseSchema";

import { requestJson } from "@/lib/api/http";

export type EntityRef =
  | { type: "experiment"; id: string }
  | { type: "gene-set"; id: string };

function basePath(ref: EntityRef): string {
  return ref.type === "experiment"
    ? `/api/v1/experiments/${ref.id}`
    : `/api/v1/gene-sets/${ref.id}`;
}

export function getAttributes(ref: EntityRef) {
  return requestJson(attributesResponseSchema, `${basePath(ref)}/results/attributes`);
}

export function getRecords(
  ref: EntityRef,
  opts?: {
    offset?: number;
    limit?: number;
    sort?: string;
    dir?: "ASC" | "DESC";
    attributes?: string[];
    filterAttribute?: string;
    filterValue?: string;
  },
) {
  const query: Record<string, string> = {};
  if (opts?.offset != null) query["offset"] = String(opts.offset);
  if (opts?.limit != null) query["limit"] = String(opts.limit);
  if (opts?.sort != null && opts.sort !== "") query["sort"] = opts.sort;
  if (opts?.dir != null) query["dir"] = opts.dir;
  if (opts?.attributes != null && opts.attributes.length > 0)
    query["attributes"] = opts.attributes.join(",");
  if (opts?.filterAttribute != null && opts.filterAttribute !== "")
    query["filterAttribute"] = opts.filterAttribute;
  if (opts?.filterValue != null) query["filterValue"] = opts.filterValue;
  return requestJson(recordsResponseSchema, `${basePath(ref)}/results/records`, {
    query,
  });
}

export function getRecordDetail(
  ref: EntityRef,
  primaryKey: { name: string; value: string }[],
) {
  return requestJson(recordDetailResponseSchema, `${basePath(ref)}/results/record`, {
    method: "POST",
    body: { primaryKey },
  });
}

export function getDistribution(ref: EntityRef, attributeName: string) {
  return requestJson(
    distributionResponseSchema,
    `${basePath(ref)}/results/distributions/${encodeURIComponent(attributeName)}`,
  );
}

export function attributesOptions(entityRef: EntityRef) {
  return queryOptions({
    queryKey: ["experiments", "attributes", entityRef.type, entityRef.id] as const,
    queryFn: () => getAttributes(entityRef),
    staleTime: 60_000,
  });
}

export function distributionOptions(entityRef: EntityRef, attr: string) {
  return queryOptions({
    queryKey: [
      "experiments",
      "distribution",
      entityRef.type,
      entityRef.id,
      attr,
    ] as const,
    queryFn: () => getDistribution(entityRef, attr),
    staleTime: 60_000,
    enabled: attr !== "",
  });
}
