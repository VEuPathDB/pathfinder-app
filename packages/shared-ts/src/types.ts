/**
 * The public type surface of @pathfinder/shared: names re-exported from the
 * Kubb-generated OpenAPI types, plus the few concepts OpenAPI does not model
 * (the site catalog, the data-part kind map, UI-only unions).
 */

import type {
  AuthStatusResponse,
  BackgroundTaskStarted,
  ColocationParams,
  CombineOp,
  ControlSetSummary,
  ControlTestResults,
  CreateConversationRequest,
  EdaAnalysisState,
  EdaDistributionSeries,
  EdaEntityCount,
  EdaSubsetPreviewPart,
  EdaVizPart,
  EdaVolcanoPoint,
  CheckedStepCount,
  ControlEnrichment,
  ControlSetEvidence,
  ControlTestEvidence,
  CriterionCitations,
  EvidenceCard,
  EvidenceVerdict,
  SiteRead,
  RequirementCheck,
  SampledGene,
  Citation,
  VerificationReview,
  LeafContribution,
  MeasuredCriterion,
  OfferedLeaf,
  SeparationOffer,
  SeparationReport,
  SkippedCriterion,
  GeneSet as GeneSetStreamPart,
  GeneSetResponse,
  GraphCleared,
  GraphSnapshot,
  InvestigationLedger,
  MemoryEditRequest,
  MemoryItem,
  MemoryListResponse,
  MemorySearchResponse,
  MemoryValue,
  ModelCatalogEntryResponse,
  ModelProvider,
  OpenConversationRequest,
  OpenConversationResponse,
  ParamSpecResponse,
  PrivacySettings,
  PrivacyUpdate,
  VariantComparison,
  VariantResult,
  ScoredComparison,
  ScoredVariant,
  ReasoningEffort,
  RecalledMemoriesPayload,
  RecalledMemory,
  RecordTypeResponse,
  ScratchpadUpdatedPayload,
  SearchResponse,
  SiteResponse,
  StepCountsResponse,
  StepResponse,
  LeadUsagePayload,
  StrategyAst,
  StrategyLink,
  StrategyMeta,
  StrategyRevisionPayload,
  StrategyStepNode,
  UserQuestionAnswer,
  VdiPublication,
  VdiPublicationRequest,
  VdiPublicationStatus,
  VdiVisibility,
  SubAgentCallPayload,
  SubAgentStepPayload,
  TurnStatusPayload,
  TurnStoppedPayload,
  TurnFailedPayload,
  ConversationTitlePayload,
  ConversationResponse,
  TaskCompleted,
  TaskListItem,
  TaskListResponse,
  TaskProgress as TaskProgressStreamPart,
  TestedParameter,
  ToolSummaryPayload,
  TurnUsage,
  UpdateConversationRequest,
  ValidationErrors,
  ValidationResponse,
  ValidationResult,
  WDKVocabTerm,
  WDKTreeBoxVocabNode,
  WDKFilterOntologyTerm,
  WDKDatasetParser,
} from "./generated/types/index";

export type ModelCatalogEntry = ModelCatalogEntryResponse;
export type Search = SearchResponse;
export type RecordType = RecordTypeResponse;
export type {
  ConversationResponse,
  CreateConversationRequest,
  OpenConversationRequest,
  OpenConversationResponse,
  StepCountsResponse,
  UpdateConversationRequest,
};
export type ParamSpec = ParamSpecResponse;
export type {
  WDKVocabTerm,
  WDKTreeBoxVocabNode,
  WDKFilterOntologyTerm,
  WDKDatasetParser,
};

export type { ValidationErrors, ValidationResponse, ValidationResult };

export type {
  VdiPublication,
  VdiPublicationRequest,
  VdiPublicationStatus,
  VdiVisibility,
};

export type { ColocationParams };

export type Step = StepResponse;
export type GeneSet = GeneSetResponse;

export type Strategy = Omit<ConversationResponse, "steps" | "isSaved"> & {
  steps: StepResponse[];
  isSaved: boolean;
};

export type { AuthStatusResponse };

export { combineOpEnum } from "./generated/types/index";
export type { CombineOp };

/** The one name each combine operator carries on every surface. */
export const COMBINE_OP_LABELS: Record<CombineOp, string> = {
  INTERSECT: "Intersect",
  UNION: "Union",
  MINUS: "Minus",
  RMINUS: "Right minus",
  LONLY: "Left only",
  RONLY: "Right only",
  COLOCATE: "Colocate",
};

export type { StrategyAst, StrategyStepNode, SiteResponse };

interface SiteName {
  id: string;
  name: string;
}

/** The site's short name, which every surface but the site menu shows. */
export function siteShortName(siteId: string): string {
  const site = VEUPATHDB_SITES.find((s) => s.id === siteId);
  return site?.name ?? siteId;
}

/** The site names the UI shows, for a label with no live site list at hand. */
const VEUPATHDB_SITES: SiteName[] = [
  {
    id: "veupathdb",
    name: "VEuPathDB",
  },
  {
    id: "plasmodb",
    name: "PlasmoDB",
  },
  {
    id: "toxodb",
    name: "ToxoDB",
  },
  {
    id: "cryptodb",
    name: "CryptoDB",
  },
  {
    id: "giardiadb",
    name: "GiardiaDB",
  },
  {
    id: "amoebadb",
    name: "AmoebaDB",
  },
  {
    id: "microsporidiadb",
    name: "MicrosporidiaDB",
  },
  {
    id: "piroplasmadb",
    name: "PiroplasmaDB",
  },
  {
    id: "tritrypdb",
    name: "TriTrypDB",
  },
  {
    id: "trichdb",
    name: "TrichDB",
  },
  {
    id: "fungidb",
    name: "FungiDB",
  },
  {
    id: "hostdb",
    name: "HostDB",
  },
  {
    id: "vectorbase",
    name: "VectorBase",
  },
  {
    id: "orthomcl",
    name: "OrthoMCL",
  },
];

export type { ModelProvider, ReasoningEffort };

export type StepKind = "search" | "transform" | "combine";

export type MemoryKind = MemoryValue["kind"];
export type {
  MemoryValue,
  MemoryItem,
  MemoryListResponse,
  MemorySearchResponse,
  MemoryEditRequest,
  RecalledMemoriesPayload,
  RecalledMemory,
};

export type { PrivacySettings, PrivacyUpdate };

export type { TaskListItem, TaskListResponse };

export type {
  GraphSnapshot,
  GraphCleared,
  StrategyMeta,
  StrategyLink,
  VariantComparison,
  VariantResult,
  ScoredComparison,
  ScoredVariant,
  BackgroundTaskStarted,
  TaskCompleted,
  TurnUsage,
  ControlTestResults,
  ControlSetSummary,
  TestedParameter,
  CheckedStepCount,
  ControlEnrichment,
  ControlSetEvidence,
  ControlTestEvidence,
  CriterionCitations,
  EvidenceCard,
  EvidenceVerdict,
  SiteRead,
  RequirementCheck,
  SampledGene,
  Citation,
  VerificationReview,
  LeafContribution,
  MeasuredCriterion,
  OfferedLeaf,
  SeparationOffer,
  SeparationReport,
  SkippedCriterion,
};
export type GeneSetPart = GeneSetStreamPart;
export type TaskProgressChunk = TaskProgressStreamPart;

export type {
  EdaAnalysisState,
  EdaDistributionSeries,
  EdaEntityCount,
  EdaVolcanoPoint,
};
export type EdaSubsetPreview = EdaSubsetPreviewPart;
export type EdaViz = EdaVizPart;

// Data-part kind to payload mapping. The renderer map is total over
// KnownDataPartKind, so a kind added here with no renderer fails to compile.

type DataConversationTitlePayload = ConversationTitlePayload;

export type DataSubAgentCallPayload = SubAgentCallPayload;
type DataSubAgentStepPayload = SubAgentStepPayload;
export type DataLeadUsagePayload = LeadUsagePayload;

export interface UserQuestionAnswersPayload {
  toolCallId: string;
  answers: UserQuestionAnswer[];
}

/** One citable source behind a research result, addressable by its url. */
export interface ResearchSourceRef {
  id: string;
  url: string;
  title?: string;
}

/**
 * The whole return value of a served research tool. One part serves both
 * tools, so only the fields they share are read here.
 */
export interface ResearchSourcesPayload {
  query: string;
  sources?: ResearchSourceRef[];
}

export type KnownDataPartKind =
  | "data-sub-agent-call"
  | "data-sub-agent-step"
  | "data-ledger-update"
  | "data-background-task-started"
  | "data-task-progress"
  | "data-task-completed"
  | "data-control-test-results"
  | "data-evidence-card"
  | "data-separation-result"
  | "data-strategy-link"
  | "data-strategy-meta"
  | "data-graph-snapshot"
  | "data-graph-cleared"
  | "data-variant-comparison"
  | "data-scored-comparison"
  | "data-memory-retrieved"
  | "data-gene-set"
  | "data-strategy-revision"
  | "data-user-question-answers"
  | "data-conversation-title"
  | "data-scratchpad-updated"
  | "data-turn-usage"
  | "data-turn-status"
  | "data-turn-stopped"
  | "data-turn-failed"
  | "data-lead-usage"
  | "data-tool-summary"
  | "data-eda.analysis-state"
  | "data-eda.subset-preview"
  | "data-eda.viz"
  | "data-research.sources";

/**
 * Kinds this app renders, plus whatever another assistant registers. An
 * unknown kind type-checks here and reaches the fallback renderer at runtime.
 */
export type DataPartKind = KnownDataPartKind | (string & {});

export interface DataPartPayloadMap {
  "data-sub-agent-call": DataSubAgentCallPayload;
  "data-sub-agent-step": DataSubAgentStepPayload;
  "data-ledger-update": InvestigationLedger;
  "data-background-task-started": BackgroundTaskStarted;
  "data-task-progress": TaskProgressStreamPart;
  "data-task-completed": TaskCompleted;
  "data-control-test-results": ControlTestResults;
  "data-evidence-card": EvidenceCard;
  "data-separation-result": SeparationReport;
  "data-strategy-link": StrategyLink;
  "data-strategy-meta": StrategyMeta;
  "data-graph-snapshot": GraphSnapshot;
  "data-graph-cleared": GraphCleared;
  "data-variant-comparison": VariantComparison;
  "data-scored-comparison": ScoredComparison;
  "data-memory-retrieved": RecalledMemoriesPayload;
  "data-gene-set": GeneSetStreamPart;
  "data-strategy-revision": StrategyRevisionPayload;
  "data-user-question-answers": UserQuestionAnswersPayload;
  "data-conversation-title": DataConversationTitlePayload;
  "data-scratchpad-updated": ScratchpadUpdatedPayload;
  "data-turn-usage": TurnUsage;
  "data-turn-status": TurnStatusPayload;
  "data-turn-stopped": TurnStoppedPayload;
  "data-turn-failed": TurnFailedPayload;
  "data-lead-usage": DataLeadUsagePayload;
  "data-tool-summary": ToolSummaryPayload;
  "data-eda.analysis-state": EdaAnalysisState;
  "data-eda.subset-preview": EdaSubsetPreviewPart;
  "data-eda.viz": EdaVizPart;
  "data-research.sources": ResearchSourcesPayload;
}
