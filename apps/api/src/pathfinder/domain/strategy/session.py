"""In-memory working state for a strategy that is under construction during a
chat session."""

from collections.abc import Mapping

from veupathdb import get_logger
from veupathdb.domain.strategy import (
    StepValidation,
    StrategyAst,
    StrategyStep,
    parent_of,
    rebuild_tree,
    root_ids,
    subtree_ids,
)
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.step_words import StampedKind, StepWords
from pathfinder.domain.strategy.types import SyncStateProtocol

logger = get_logger(__name__)


class StrategyHistoryEntry(CamelModel):
    """One undo history entry. The history is transient and rebuilds on load."""

    description: str
    strategy_ast: StrategyAst


class StrategyGraph:
    """State for a single strategy graph."""

    def __init__(self, graph_id: str, name: str, site_id: str) -> None:
        self.id = graph_id
        self.name = name
        self.site_id = site_id
        # The record type is set on the first step or on import of a strategy.
        self.record_type: str | None = None
        self.description: str | None = None
        self.steps: dict[str, StrategyStep] = {}
        # A root is a step that no other step consumes. A complete strategy has
        # exactly one root.
        self.roots: set[str] = set()
        self.history: list[StrategyHistoryEntry] = []
        self.last_step_id: str | None = None
        # The researcher's words each step stands for, keyed by step id.
        self.criterion_texts: dict[str, str] = {}
        # Which plugin reads the analysis document of each EDA step.
        self.analysis_kinds: dict[str, StampedKind] = {}
        # The searches whose catalog read failed. Each turn builds its own graph,
        # so this holds for one turn, and it is never stored.
        self.unreadable_searches: set[str] = set()

    def note_criteria(self, texts: Mapping[str, str]) -> None:
        """Take the words for the steps the graph holds, and forget the rest."""
        merged = {**self.criterion_texts, **texts}
        self.criterion_texts = {
            sid: text for sid, text in merged.items() if sid in self.steps
        }

    def analysis_kind_of(self, step_id: str) -> AnalysisKind | None:
        """The step's kind, when it was read for the search the step runs now."""
        stamped = self.analysis_kinds.get(step_id)
        step = self.steps.get(step_id)
        if stamped is None or step is None:
            return None
        return stamped.for_search(step.search_name)

    def note_analysis_kinds(self, kinds: Mapping[str, StampedKind]) -> None:
        """Take the kinds for the steps the graph holds, and forget the rest."""
        merged = {**self.analysis_kinds, **kinds}
        self.analysis_kinds = {
            sid: kind for sid, kind in merged.items() if sid in self.steps
        }

    def primary_root_id(self) -> str | None:
        """Return the root of the main strategy tree.

        The largest subtree wins. A tie goes to the step that was added first,
        so the result is stable across calls.
        """
        if not self.roots:
            return None
        if len(self.roots) == 1:
            return next(iter(self.roots))
        ordered = [sid for sid in self.steps if sid in self.roots]
        return max(
            ordered,
            key=lambda sid: (self.subtree_size(sid), -ordered.index(sid)),
        )

    def subtree_size(self, step_id: str) -> int:
        return len(subtree_ids(step_id, self.steps))

    def to_strategy_ast(
        self,
        root_step_id: str | None = None,
        sync_state: SyncStateProtocol | None = None,
        *,
        include_detached: bool = True,
    ) -> StrategyAst | None:
        """Produce a typed plan payload for API responses and persistence.

        With ``include_detached=False`` the payload holds only the subtree
        under the root, which is the shape WDK accepts.
        """
        root_id = root_step_id or self.primary_root_id()
        if root_id is None or root_id not in self.steps:
            return None
        root = rebuild_tree(root_id, self.steps)
        detached = (
            [
                rebuild_tree(sid, self.steps)
                for sid in self.steps
                if sid in self.roots and sid != root_id
            ]
            if include_detached
            else []
        )

        step_counts: dict[str, int] | None = None
        wdk_step_ids: dict[str, int] | None = None
        step_validations: dict[str, StepValidation] | None = None
        wdk_push_errors: dict[str, str] | None = None
        if sync_state is not None:
            if sync_state.step_counts:
                step_counts = {
                    k: v for k, v in sync_state.step_counts.items() if v is not None
                }
            if sync_state.wdk_step_ids:
                wdk_step_ids = dict(sync_state.wdk_step_ids)
            if sync_state.step_validations:
                step_validations = dict(sync_state.step_validations)
            if sync_state.wdk_push_errors:
                wdk_push_errors = dict(sync_state.wdk_push_errors)

        words = StepWords(
            criterion_texts={
                s: t for s, t in self.criterion_texts.items() if s in self.steps
            },
            analysis_kinds={
                s: k for s, k in self.analysis_kinds.items() if s in self.steps
            },
        )
        return StrategyAst(
            record_type=self.record_type or "",
            root=root,
            detached_roots=detached,
            name=self.name,
            description=self.description or None,
            metadata=(
                words.model_dump(by_alias=True, mode="json")
                if words.criterion_texts or words.analysis_kinds
                else None
            ),
            step_counts=step_counts,
            wdk_step_ids=wdk_step_ids,
            step_validations=step_validations,
            wdk_push_errors=wdk_push_errors,
        )

    def parent_of(self, step_id: str) -> tuple[StrategyStep, str] | None:
        """Return the parent of a step and the input slot it occupies, or
        ``None`` when the step is a root or is absent."""
        return parent_of(step_id, self.steps)

    def get_step(self, step_id: str) -> StrategyStep | None:
        return self.steps.get(step_id)

    def recompute_roots(self) -> None:
        """Recompute the root set from the current steps. Call this after a
        bulk mutation such as a delete or a hydration."""
        self.roots = root_ids(self.steps)

    def save_history(self, description: str) -> None:
        """Save current state to history."""
        ast = self.to_strategy_ast()
        if ast is not None:
            self.history.append(
                StrategyHistoryEntry(description=description, strategy_ast=ast),
            )


def strategy_root_id(
    graph: StrategyGraph, sync_state: SyncStateProtocol | None
) -> str | None:
    """The step whose count the strategy is cited with.

    A split graph is cited with the root the last push made the WDK
    strategy's root step. Nothing when the graph is split and no push names
    one. Structural root identity stays with ``primary_root_id``.
    """
    if len(graph.roots) == 1:
        return next(iter(graph.roots))
    if sync_state is None:
        return None
    wdk_root = sync_state.wdk_root_step_id
    if wdk_root is None:
        return None
    return next(
        (sid for sid in graph.roots if sync_state.wdk_step_ids.get(sid) == wdk_root),
        None,
    )


class StrategySession:
    """Session context for the active strategy (graph + chat)."""

    def __init__(self, site_id: str) -> None:
        self.site_id = site_id
        self.graph: StrategyGraph | None = None
        self.sync_state: SyncStateProtocol | None = None

    def add_graph(self, graph: StrategyGraph) -> None:
        """Register a graph in the session. A session holds one graph, so a
        second, different graph is ignored."""
        if self.graph and self.graph.id != graph.id:
            logger.warning(
                "Ignoring add_graph: session already has an active graph",
                active_graph_id=self.graph.id,
                rejected_graph_id=graph.id,
            )
            return
        self.graph = graph

    def get_graph(self, graph_id: str | None) -> StrategyGraph | None:
        """Return the graph with this id, or the active graph when the id is
        ``None``."""
        if not self.graph:
            return None
        if graph_id is None or graph_id == self.graph.id:
            return self.graph
        return None
