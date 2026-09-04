/**
 * The public type surface of @pathfinder/shared: names re-exported from the
 * Kubb-generated OpenAPI types, plus the few concepts OpenAPI does not model
 * (the site catalog, the data-part kind map, UI-only unions).
 */

import type {
  AuthStatusResponse,
  BackgroundTaskStarted,
  BootstrapResult,
  Classification,
  ColocationParams,
  CombineOp,
  ConfidenceInterval,
  ConfusionMatrix,
  ControlSetResponse,
  CreateConversationRequest,
  CrossValidationResult,
  EdaAnalysisState,
  EdaDistributionSeries,
  EdaEntityCount,
  EdaSubsetPreviewPart,
  EdaVizPart,
  EdaVolcanoPoint,
  EnrichmentAnalysisType,
  EnrichmentResult,
  EnrichmentTerm,
  ExperimentConfig,
  ExperimentMetrics,
  Experiment,
  GeneInfo,
  GeneResolveResponse,
  GeneSearchResponse,
  GeneSearchResultResponse,
  GeneSet as GeneSetStreamPart,
  GeneSetResponse,
  GraphCleared,
  GraphSnapshot,
  InvestigationLedger,
  MessagesCompleteEvent,
  MessagesPartialEvent,
  MemoryEditRequest,
  MemoryItem,
  MemoryListResponse,
  MemoryRetrievedPayload,
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
  ScoredComparison,
  ScoredVariant,
  ReasoningEffort,
  RecordTypeResponse,
  ResolvedGeneResponse,
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
  SubAgentCallPayload,
  SubAgentStepPayload,
  TurnStatusPayload,
  TurnStoppedPayload,
  TurnFailedPayload,
  ConversationTitlePayload,
  ConversationResponse,
  EnrichmentResultsChunk,
  TaskCompleted,
  TaskListItem,
  TaskListResponse,
  TaskProgress as TaskProgressStreamPart,
  ToolCallDelta,
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

export type { MessagesPartialEvent, MessagesCompleteEvent, ToolCallDelta };

export type ModelCatalogEntry = ModelCatalogEntryResponse;
export type GeneSearchResult = GeneSearchResultResponse;
export type { GeneSearchResponse, GeneResolveResponse };
export type ResolvedGene = ResolvedGeneResponse;
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
  BootstrapResult,
  ConfidenceInterval,
  ConfusionMatrix,
  CrossValidationResult,
  EnrichmentResult,
  EnrichmentTerm,
  Experiment,
  ExperimentConfig,
  ExperimentMetrics,
  GeneInfo,
};

export type { ColocationParams };

export type Step = StepResponse;
export type GeneSet = GeneSetResponse;
export type ControlSet = ControlSetResponse;

export type Strategy = Omit<ConversationResponse, "steps" | "isSaved"> & {
  steps: StepResponse[];
  isSaved: boolean;
};

export type { AuthStatusResponse };

export { combineOpEnum } from "./generated/types/index";
export type { CombineOp };

export const CombineOpBadgeLabels: Record<CombineOp, string> = {
  INTERSECT: "AND (INTERSECT)",
  MINUS: "NOT (MINUS LEFT)",
  RMINUS: "NOT (MINUS RIGHT)",
  LONLY: "LEFT ONLY",
  RONLY: "RIGHT ONLY",
  COLOCATE: "NEAR (COLOCATE)",
  UNION: "OR (UNION)",
};

export type { StrategyAst, StrategyStepNode, SiteResponse };

export function siteDisplayName(siteId: string): string {
  const site = VEUPATHDB_SITES.find((s) => s.id === siteId);
  return site?.displayName ?? site?.name ?? siteId;
}

/** The site's brand name, for a label with no room for the long form. */
export function siteShortName(siteId: string): string {
  const site = VEUPATHDB_SITES.find((s) => s.id === siteId);
  return site?.name ?? siteId;
}

const VEUPATHDB_SITES: SiteResponse[] = [
  {
    id: "veupathdb",
    name: "VEuPathDB",
    displayName: "VEuPathDB Portal (All organisms)",
    baseUrl: "https://veupathdb.org",
    projectId: "EuPathDB",
    isPortal: true,
  },
  {
    id: "plasmodb",
    name: "PlasmoDB",
    displayName: "PlasmoDB (Plasmodium)",
    baseUrl: "https://plasmodb.org",
    projectId: "PlasmoDB",
    isPortal: false,
  },
  {
    id: "toxodb",
    name: "ToxoDB",
    displayName: "ToxoDB (Toxoplasma)",
    baseUrl: "https://toxodb.org",
    projectId: "ToxoDB",
    isPortal: false,
  },
  {
    id: "cryptodb",
    name: "CryptoDB",
    displayName: "CryptoDB (Cryptosporidium)",
    baseUrl: "https://cryptodb.org",
    projectId: "CryptoDB",
    isPortal: false,
  },
  {
    id: "giardiadb",
    name: "GiardiaDB",
    displayName: "GiardiaDB (Giardia)",
    baseUrl: "https://giardiadb.org",
    projectId: "GiardiaDB",
    isPortal: false,
  },
  {
    id: "amoebadb",
    name: "AmoebaDB",
    displayName: "AmoebaDB (Amoeba)",
    baseUrl: "https://amoebadb.org",
    projectId: "AmoebaDB",
    isPortal: false,
  },
  {
    id: "microsporidiadb",
    name: "MicrosporidiaDB",
    displayName: "MicrosporidiaDB (Microsporidia)",
    baseUrl: "https://microsporidiadb.org",
    projectId: "MicrosporidiaDB",
    isPortal: false,
  },
  {
    id: "piroplasmadb",
    name: "PiroplasmaDB",
    displayName: "PiroplasmaDB (Piroplasma)",
    baseUrl: "https://piroplasmadb.org",
    projectId: "PiroplasmaDB",
    isPortal: false,
  },
  {
    id: "tritrypdb",
    name: "TriTrypDB",
    displayName: "TriTrypDB (Kinetoplastids)",
    baseUrl: "https://tritrypdb.org",
    projectId: "TriTrypDB",
    isPortal: false,
  },
  {
    id: "trichdb",
    name: "TrichDB",
    displayName: "TrichDB (Trichomonas)",
    baseUrl: "https://trichdb.org",
    projectId: "TrichDB",
    isPortal: false,
  },
  {
    id: "fungidb",
    name: "FungiDB",
    displayName: "FungiDB (Fungi)",
    baseUrl: "https://fungidb.org",
    projectId: "FungiDB",
    isPortal: false,
  },
  {
    id: "hostdb",
    name: "HostDB",
    displayName: "HostDB (Hosts)",
    baseUrl: "https://hostdb.org",
    projectId: "HostDB",
    isPortal: false,
  },
  {
    id: "vectorbase",
    name: "VectorBase",
    displayName: "VectorBase (Vectors)",
    baseUrl: "https://vectorbase.org",
    projectId: "VectorBase",
    isPortal: false,
  },
  {
    id: "orthomcl",
    name: "OrthoMCL",
    displayName: "OrthoMCL (Orthologs)",
    baseUrl: "https://orthomcl.org",
    projectId: "OrthoMCL",
    isPortal: false,
  },
];

export type {
  Classification,
  EnrichmentAnalysisType,
  ModelProvider,
  ReasoningEffort,
};

export type StepKind = "search" | "transform" | "combine";

export type MemoryKind = MemoryValue["kind"];
export type {
  MemoryValue,
  MemoryItem,
  MemoryListResponse,
  MemorySearchResponse,
  MemoryEditRequest,
};

export type { PrivacySettings, PrivacyUpdate };

export type { TaskListItem, TaskListResponse };

export type {
  GraphSnapshot,
  GraphCleared,
  StrategyMeta,
  StrategyLink,
  VariantComparison,
  ScoredComparison,
  ScoredVariant,
  BackgroundTaskStarted,
  TaskCompleted,
  TurnUsage,
  EnrichmentResultsChunk,
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

export type KnownDataPartKind =
  | "data-sub-agent-call"
  | "data-sub-agent-step"
  | "data-ledger-update"
  | "data-background-task-started"
  | "data-task-progress"
  | "data-task-completed"
  | "data-enrichment-results"
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
  | "data-eda.viz";

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
  "data-enrichment-results": EnrichmentResultsChunk;
  "data-strategy-link": StrategyLink;
  "data-strategy-meta": StrategyMeta;
  "data-graph-snapshot": GraphSnapshot;
  "data-graph-cleared": GraphCleared;
  "data-variant-comparison": VariantComparison;
  "data-scored-comparison": ScoredComparison;
  "data-memory-retrieved": MemoryRetrievedPayload;
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
}
