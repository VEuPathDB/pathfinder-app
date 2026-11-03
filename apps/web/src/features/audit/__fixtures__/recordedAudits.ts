import { missingGeneAuditSchema } from "@pathfinder/shared/generated/zod/missingGeneAuditSchema";
import { selenoproteinEndAuditSchema } from "@pathfinder/shared/generated/zod/selenoproteinEndAuditSchema";

export const SELK_STOPS_AT_SEC = selenoproteinEndAuditSchema.parse({
  verdict: "STOPS_AT_SEC",
  afterModelEnd: "*G*",
  referenceTail: "UG",
  tailIdentity: 1.0,
  secAligned: true,
  geneIds: [
    { given: "TGGT1_316600", resolved: "TGGT1_316600" },
    { given: "TGME49_316600", resolved: "TGME49_316600" },
  ],
  gene: "TGGT1_316600",
  referenceGene: "TGME49_316600",
});

export const NAC_MISSING_IN_GT1 = missingGeneAuditSchema.parse({
  verdict: "IN_DNA_UNANNOTATED",
  geneIds: [{ given: "TGARI_257090", resolved: "TGARI_257090" }],
  exampleGene: "TGARI_257090",
  absentOrganism: "Toxoplasma gondii GT1",
  exampleLength: 359,
  annotatedMembers: [],
  anchors: {
    left: {
      neighbour: "TGARI_257070",
      gene: "TGGT1_257070",
      sequenceId: "TGGT1_chrVIIb",
      start: 4176004,
      end: 4180213,
      strand: "-",
    },
    right: {
      neighbour: "TGARI_257100",
      gene: "TGGT1_257100",
      sequenceId: "TGGT1_chrVIIb",
      start: 4153116,
      end: 4154810,
      strand: "+",
    },
    between: [4154810, 4176004],
  },
  located: { windows: 34, found: 34, span: [4156680, 4157729], ns: 0, share: 1 },
  overlapping: [],
  openFrame: { length: 196, identical: 196 },
  stops: [163],
  intactFrame: false,
  code: "standard",
  codeInferred: true,
});
