export const RUN = "00000000-0000-4000-8000-000000000001";

export const SAMPLE_RUN = {
  run: {
    id: RUN,
    site_id: "plasmodb",
    conversation_id: "00000000-0000-4000-8000-000000000002",
    release: "71",
    status: "finished",
    phase: "finished",
    deadline_at: null,
    genomes: ["Examplea alpha A"],
    checks: ["gene_length", "intron_support"],
    targets: 0,
    created_at: "2026-10-22T00:00:00Z",
    finished_at: "2026-10-22T00:00:00Z",
  },
  requests: 21,
  store_reads: 45,
  unfinished: [],
  reviewed: 0,
  reviews_running: false,
};

export function detail(id: number) {
  return {
    site_id: "plasmodb",
    finding: {
      id,
      genome: "Examplea alpha A",
      screened_genome: "Examplea alpha A",
      paired_genome: null,
      sampled: false,
      status: "confirmed",
      error_type: "truncated_model",
      genes: [{ gene: "EXA_0001" }],
    },
    evidence: [],
  };
}
