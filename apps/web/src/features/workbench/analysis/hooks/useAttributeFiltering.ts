import { useState } from "react";
import { useSuspenseQuery } from "@tanstack/react-query";
import type { RecordAttribute } from "@pathfinder/shared/generated/types/RecordAttribute";
import {
  attributesOptions,
  type EntityRef,
} from "@/features/workbench/analysis/api/stepResults";
import { isDistributableAttr } from "@/features/workbench/analysis/components/DistributionExplorer/attributeFilters";

interface AttributeFilteringState {
  attributes: RecordAttribute[];
  selectedAttr: string;
  setSelectedAttr: (attr: string) => void;
}

export function useAttributeFiltering(entityRef: EntityRef): AttributeFilteringState {
  const { data: attributes } = useSuspenseQuery({
    ...attributesOptions(entityRef),
    select: (raw) => raw.attributes.filter(isDistributableAttr),
  });

  const firstAttrName = attributes[0]?.name ?? "";
  const [selectedAttr, setSelectedAttr] = useState(firstAttrName);
  const [prevFirstAttr, setPrevFirstAttr] = useState(firstAttrName);
  if (firstAttrName !== prevFirstAttr) {
    setPrevFirstAttr(firstAttrName);
    setSelectedAttr(firstAttrName);
  }

  return {
    attributes,
    selectedAttr,
    setSelectedAttr,
  };
}
