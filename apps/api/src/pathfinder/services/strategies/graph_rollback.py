"""What a batch writes on a graph beside its steps, and how a refused batch puts
the graph back."""

from pydantic import BaseModel, ConfigDict, Field
from veupathdb.domain.strategy import StrategyAst, flatten_tree

from pathfinder.domain.strategy.operations import ReplaceStrategyOp
from pathfinder.domain.strategy.operations.apply import apply_operation
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.step_words import StepWords


class GraphLabels(BaseModel):
    """What a batch writes on the graph itself, beside its steps."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str | None = None
    last_step_id: str | None = None
    words: StepWords = Field(default_factory=StepWords)


def graph_labels(graph: StrategyGraph) -> GraphLabels:
    """The name, the description, the write cursor and the words it carries now."""
    return GraphLabels(
        name=graph.name,
        description=graph.description,
        last_step_id=graph.last_step_id,
        words=graph.words,
    )


def restore_graph(
    graph: StrategyGraph, old_ast: StrategyAst | None, entry: GraphLabels
) -> None:
    """Put the graph back the way it was before a failed batch.

    ``apply_operation`` edits the live nodes, so a batch that fails partway
    has already changed the graph. Replaying the pre-batch tree and the labels
    it carried is what makes a rejected batch a no-op rather than a
    half-applied edit. A graph with no tree to replay takes its labels back
    the same way.
    """
    graph.steps.clear()
    graph.roots.clear()
    if old_ast is not None:
        apply_operation(graph, ReplaceStrategyOp(root=old_ast.root))
        for detached in old_ast.detached_roots:
            graph.steps.update(flatten_tree(detached))
        graph.recompute_roots()
    graph.name = entry.name
    graph.description = entry.description
    graph.last_step_id = entry.last_step_id
    graph.words = entry.words
