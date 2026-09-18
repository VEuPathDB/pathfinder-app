import { queryOptions } from "@tanstack/react-query";
import type {
  ParamSpec,
  RecordType,
  Search,
  SiteResponse,
  ValidationResponse,
} from "@pathfinder/shared";
import { paramSpecResponseSchema } from "@pathfinder/shared/generated/zod/paramSpecResponseSchema";
import { recordTypeResponseSchema } from "@pathfinder/shared/generated/zod/recordTypeResponseSchema";
import { searchResponseSchema } from "@pathfinder/shared/generated/zod/searchResponseSchema";
import { siteResponseSchema } from "@pathfinder/shared/generated/zod/siteResponseSchema";
import { validationResponseSchema } from "@pathfinder/shared/generated/zod/validationResponseSchema";
import { z } from "zod";

import type { DependentParamsRequest } from "@pathfinder/shared/generated/types/DependentParamsRequest";
import type { ParamSpecsRequest } from "@pathfinder/shared/generated/types/ParamSpecsRequest";
import type { SearchValidationRequest } from "@pathfinder/shared/generated/types/SearchValidationRequest";
import type { StepParameters } from "@/lib/types/stepParameters";
import { requestJson } from "./http";

const SiteListSchema = z.array(siteResponseSchema);
const RecordTypeListSchema = z.array(recordTypeResponseSchema);
const SearchListSchema = z.array(searchResponseSchema);
const ParamSpecListSchema = z.array(paramSpecResponseSchema);

export async function listSites(): Promise<SiteResponse[]> {
  return await requestJson(SiteListSchema, "/api/v1/sites");
}

export async function getRecordTypes(siteId: string): Promise<RecordType[]> {
  return await requestJson(
    RecordTypeListSchema,
    `/api/v1/sites/${encodeURIComponent(siteId)}/record-types`,
  );
}

export async function getSearches(
  siteId: string,
  recordType?: string | null,
): Promise<Search[]> {
  return await requestJson(
    SearchListSchema,
    `/api/v1/sites/${encodeURIComponent(siteId)}/searches`,
    recordType != null && recordType !== "" ? { query: { recordType } } : {},
  );
}

export async function getParamSpecs(
  siteId: string,
  recordType: string,
  searchName: string,
  contextValues: StepParameters = {},
): Promise<ParamSpec[]> {
  return await requestJson(
    ParamSpecListSchema,
    `/api/v1/sites/${encodeURIComponent(siteId)}/searches/${encodeURIComponent(
      recordType,
    )}/${encodeURIComponent(searchName)}/param-specs`,
    { method: "POST", body: { contextValues } satisfies ParamSpecsRequest },
  );
}

export async function refreshDependentParams(
  siteId: string,
  recordType: string,
  searchName: string,
  parameterName: string,
  contextValues: StepParameters = {},
): Promise<ParamSpec[]> {
  return await requestJson(
    ParamSpecListSchema,
    `/api/v1/sites/${encodeURIComponent(siteId)}/searches/${encodeURIComponent(
      recordType,
    )}/${encodeURIComponent(searchName)}/refreshed-dependent-params`,
    {
      method: "POST",
      body: { parameterName, contextValues } satisfies DependentParamsRequest,
    },
  );
}

export async function validateSearchParams(
  siteId: string,
  recordType: string,
  searchName: string,
  contextValues: StepParameters = {},
): Promise<ValidationResponse> {
  return await requestJson(
    validationResponseSchema,
    `/api/v1/sites/${encodeURIComponent(siteId)}/searches/${encodeURIComponent(
      recordType,
    )}/${encodeURIComponent(searchName)}/validate`,
    { method: "POST", body: { contextValues } satisfies SearchValidationRequest },
  );
}

// The api retries a degraded site on the same interval, so a recovered site
// clears its warning without a reload.
const SITE_AVAILABILITY_INTERVAL_MS = 60_000;

export function sitesOptions() {
  return queryOptions({
    queryKey: ["sites"] as const,
    queryFn: listSites,
    staleTime: SITE_AVAILABILITY_INTERVAL_MS,
    refetchInterval: SITE_AVAILABILITY_INTERVAL_MS,
  });
}

export function recordTypesOptions(siteId: string) {
  return queryOptions({
    queryKey: ["sites", siteId, "record-types"] as const,
    queryFn: () => getRecordTypes(siteId),
    staleTime: 5 * 60_000,
    enabled: siteId !== "",
  });
}

export function searchesOptions(siteId: string, recordType?: string | null) {
  return queryOptions({
    queryKey: ["sites", siteId, "searches", recordType ?? "all"] as const,
    queryFn: () => getSearches(siteId, recordType),
    staleTime: 5 * 60_000,
    enabled: siteId !== "",
  });
}

export function paramSpecsOptions(
  siteId: string,
  recordType: string,
  searchName: string,
) {
  return queryOptions({
    queryKey: ["sites", siteId, "param-specs", recordType, searchName] as const,
    queryFn: () => getParamSpecs(siteId, recordType, searchName),
    staleTime: 5 * 60_000,
    enabled: siteId !== "" && recordType !== "" && searchName !== "",
  });
}
