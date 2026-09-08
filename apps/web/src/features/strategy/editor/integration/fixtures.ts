/**
 * Shared test fixtures for RHF-22 / RHF-23 integration and edge-case tests.
 *
 * Realistic WDK parameter specs modeled after actual PlasmoDB searches
 * (GenesByMolecularWeight, GenesByTextSearch, GO enrichment).
 */

import type { ParamSpec } from "@pathfinder/shared";
import type { VocabOption } from "@/lib/utils/vocab";

export function makeSpec(overrides: Partial<ParamSpec> = {}): ParamSpec {
  return {
    name: "test_param",
    type: "string",
    displayName: "Test",
    displayType: "",
    allowEmptyValue: true,
    isVisible: true,
    isNumber: false,
    countOnlyLeaves: false,
    initialDisplayValue: "",
    allowMultipleValues: false,
    multiPick: false,
    minSelectedCount: null,
    maxSelectedCount: null,
    vocabulary: null,
    min: null,
    max: null,
    increment: null,
    group: null,
    help: null,
    ...overrides,
  };
}

/** Realistic specs for GenesByMolecularWeight: organism select + numeric range. */
export function molecularWeightSpecs(): ParamSpec[] {
  return [
    makeSpec({
      name: "organism",
      type: "string",
      displayName: "Organism",
      displayType: "select",
      allowEmptyValue: false,
      initialDisplayValue: "Plasmodium falciparum 3D7",
    }),
    makeSpec({
      name: "min_molecular_weight",
      type: "number",
      displayName: "Min Molecular Weight",
      displayType: "",
      allowEmptyValue: true,
      isNumber: true,
      initialDisplayValue: "0",
      min: 0,
      max: 1000000,
    }),
    makeSpec({
      name: "max_molecular_weight",
      type: "number",
      displayName: "Max Molecular Weight",
      displayType: "",
      allowEmptyValue: true,
      isNumber: true,
      initialDisplayValue: "1000000",
      min: 0,
      max: 1000000,
    }),
  ];
}

export const organismOptions: VocabOption[] = [
  { value: "Plasmodium falciparum 3D7", label: "P. falciparum 3D7" },
  { value: "Plasmodium vivax Sal-1", label: "P. vivax Sal-1" },
  { value: "Toxoplasma gondii ME49", label: "T. gondii ME49" },
];

/** Multi-pick specs for GO enrichment. */
export function multiPickSpecs(): ParamSpec[] {
  return [
    makeSpec({
      name: "go_terms",
      type: "string",
      displayName: "GO Terms",
      displayType: "checkbox",
      allowEmptyValue: true,
      allowMultipleValues: true,
      initialDisplayValue: "[]",
    }),
  ];
}

export const goOptions: VocabOption[] = [
  { value: "GO:0006915", label: "apoptotic process" },
  { value: "GO:0006916", label: "anti-apoptosis" },
  { value: "GO:0006950", label: "response to stress" },
  { value: "GO:0007049", label: "cell cycle" },
  { value: "GO:0008150", label: "biological process" },
];

/** Alternative specs for search-switch test (GenesByTextSearch). */
export function textSearchSpecs(): ParamSpec[] {
  return [
    makeSpec({
      name: "text_expression",
      type: "string",
      displayName: "Text Term",
      displayType: "",
      allowEmptyValue: false,
      initialDisplayValue: "",
    }),
    makeSpec({
      name: "text_fields",
      type: "string",
      displayName: "Fields to Search",
      displayType: "checkbox",
      allowMultipleValues: true,
      initialDisplayValue: '["Gene ID","Product Description"]',
    }),
  ];
}
