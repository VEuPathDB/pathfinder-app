"use client";

import { useState } from "react";
import { useSuspenseQuery } from "@tanstack/react-query";
import type { RecordType } from "@strategist/shared";
import { recordTypesOptions } from "@/lib/api/sites";
import { normalizeRecordType } from "@/lib/utils/normalizeRecordType";

interface UseStepRecordTypeArgs {
  siteId: string;
  /** The record type passed in from the parent (strategy-level). */
  recordType: string | null;
  /** Initial record type value from the step. */
  initialRecordType: string | null | undefined;
}

export function useStepRecordType({
  siteId,
  recordType,
  initialRecordType,
}: UseStepRecordTypeArgs) {
  const [recordTypeValue, setRecordTypeValue] = useState(
    normalizeRecordType(initialRecordType ?? recordType),
  );
  const [recordTypeFilter, setRecordTypeFilter] = useState("");

  const { enabled: _enabled, ...recordTypeOpts } = recordTypesOptions(siteId);
  const { data: rawRecordTypes } = useSuspenseQuery(recordTypeOpts);

  const recordTypeOptions: RecordType[] = [...rawRecordTypes].sort((a, b) =>
    (a.displayName || a.name).localeCompare(b.displayName || b.name),
  );

  const validatedRecordTypeValue = (() => {
    if (recordTypeOptions.length === 0) return recordTypeValue;
    if (recordTypeValue == null || recordTypeValue === "") return recordTypeValue;
    const normalized = normalizeRecordType(recordTypeValue);
    const exists = recordTypeOptions.some((option) => option.name === normalized);
    return exists ? recordTypeValue : "";
  })();

  const normalizedRecordTypeValue = normalizeRecordType(validatedRecordTypeValue);
  const apiRecordTypeValue = normalizedRecordTypeValue;

  const resolveRecordTypeForSearch = (searchRecordType?: string | null) => {
    const normalized = normalizeRecordType(searchRecordType ?? "");
    if (normalized != null && normalized !== "") {
      const exists = recordTypeOptions.some((option) => option.name === normalized);
      if (exists) return normalized;
    }
    return normalizeRecordType(validatedRecordTypeValue ?? recordType) ?? "";
  };

  const filteredRecordTypes = (() => {
    const query = recordTypeFilter.trim().toLowerCase();
    if (query === "") return recordTypeOptions;
    return recordTypeOptions.filter((option) => {
      const label = (option.displayName || option.name).toLowerCase();
      return label.includes(query) || option.name.toLowerCase().includes(query);
    });
  })();

  return {
    recordTypeValue: validatedRecordTypeValue,
    setRecordTypeValue,
    normalizedRecordTypeValue,
    apiRecordTypeValue,
    recordTypeFilter,
    setRecordTypeFilter,
    recordTypeOptions,
    filteredRecordTypes,
    resolveRecordTypeForSearch,
  };
}
