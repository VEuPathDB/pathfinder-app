"""Validates a strategy tree and reports the issues it finds."""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from pydantic import ConfigDict, JsonValue
from veupathdb.domain.parameters import to_decoded_map
from veupathdb.domain.strategy import CombineOp, StrategyStepNode
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.organism_scope import dataset_leaf, output_organisms


def _scope_text(scope: set[str]) -> str:
    return ", ".join(sorted(scope))


def _path_to(node: StrategyStepNode, step_id: str) -> list[StrategyStepNode] | None:
    """The nodes from this one down to the step, the step last."""
    if node.id == step_id:
        return [node]
    for child in node.inputs():
        below = _path_to(child, step_id)
        if below is not None:
            return [node, *below]
    return None


def _transforms_above(
    root: StrategyStepNode,
    combine: StrategyStepNode,
    marked: Mapping[str, str],
    datasets: Mapping[str, frozenset[str]],
) -> list[tuple[str, set[str]]]:
    """The transforms the combine sits under that change the organism, nearest
    first. A transform beside the combine cannot hold the combine's criteria."""
    found: list[tuple[str, set[str]]] = []
    for node in reversed(_path_to(root, combine.id) or []):
        source = node.primary_input
        if node.infer_kind() != "transform" or source is None:
            continue
        output = output_organisms(node, marked, datasets)
        if output is not None and output != output_organisms(source, marked, datasets):
            found.append((node.search_name, output))
    return found


def _dataset_remedy(
    combine: StrategyStepNode,
    scopes: tuple[set[str], set[str]],
    marked: Mapping[str, str],
    datasets: Mapping[str, frozenset[str]],
) -> str | None:
    """The transform that maps a side whose dataset fixes its organism, or None
    when no side runs on a dataset."""
    leaves = [dataset_leaf(side, marked, datasets) for side in combine.inputs()]
    if all(leaf is not None for leaf in leaves):
        return (
            "Each side runs on an experiment, and no parameter changes its "
            "organism. Map one side to the organism of the other with a "
            "GenesByOrthologs transform."
        )
    for leaf, own, other in zip(leaves, scopes, reversed(scopes), strict=True):
        if leaf is not None:
            return (
                f"The {leaf.search_name} search runs on an experiment of "
                f"{_scope_text(own)}, and no parameter changes that organism. "
                f"Map that side to {_scope_text(other)} with a GenesByOrthologs "
                f"transform."
            )
    return None


def _remedy(
    root: StrategyStepNode,
    combine: StrategyStepNode,
    scopes: tuple[set[str], set[str]],
    marked: Mapping[str, str],
    datasets: Mapping[str, frozenset[str]],
) -> str:
    """The edit that makes the two scopes meet."""
    for search_name, output in _transforms_above(root, combine, marked, datasets):
        for side in scopes:
            if output == side:
                return (
                    f"Move the {_scope_text(side)} criteria above the "
                    f"{search_name} transform."
                )
    by_dataset = _dataset_remedy(combine, scopes, marked, datasets)
    if by_dataset is not None:
        return by_dataset
    return (
        f"Scope every seed to one organism: {_scope_text(scopes[0])} or "
        f"{_scope_text(scopes[1])}."
    )


def cross_organism_refusal(
    combine: StrategyStepNode,
    root: StrategyStepNode,
    organism_params: Mapping[str, str],
    dataset_organisms: Mapping[str, frozenset[str]],
) -> str | None:
    """Why the combine returns nothing, or None when its inputs can meet.

    Gene ids from different organisms never match, so an INTERSECT of two known
    and disjoint scopes is always empty. A search reads its organism from the
    parameter it marks, or from its dataset when it marks none.
    """
    if combine.operator is not CombineOp.INTERSECT:
        return None
    if combine.primary_input is None or combine.secondary_input is None:
        return None
    primary = output_organisms(
        combine.primary_input, organism_params, dataset_organisms
    )
    secondary = output_organisms(
        combine.secondary_input, organism_params, dataset_organisms
    )
    if primary is None or secondary is None or not primary.isdisjoint(secondary):
        return None
    remedy = _remedy(
        root, combine, (primary, secondary), organism_params, dataset_organisms
    )
    return (
        f"Cannot INTERSECT steps with different organism scopes "
        f"({_scope_text(primary)} vs {_scope_text(secondary)}). Gene IDs from "
        f"different organisms never match, so this always returns 0 results. "
        f"{remedy}"
    )


def first_cross_organism_refusal(
    root: StrategyStepNode,
    organism_params: Mapping[str, str],
    dataset_organisms: Mapping[str, frozenset[str]],
) -> str | None:
    """Why the first INTERSECT of the tree that can never meet is refused, or None."""
    for node in _nodes(root):
        refusal = cross_organism_refusal(node, root, organism_params, dataset_organisms)
        if refusal is not None:
            return refusal
    return None


def _nodes(node: StrategyStepNode) -> Iterator[StrategyStepNode]:
    yield node
    for child in node.inputs():
        yield from _nodes(child)


class SearchRecordClasses(CamelModel):
    """The record class a search returns and the classes its input step may
    hold, as WDK declares them; ``takes`` is empty for a search with no input."""

    model_config = ConfigDict(frozen=True)

    display_name: str
    returns: str
    takes: tuple[str, ...] = ()


def _returned_classes(
    node: StrategyStepNode, classes: Mapping[str, SearchRecordClasses]
) -> set[str]:
    """The known record classes a subtree returns. A combine returns the
    classes of its inputs, and one of unknown class adds none."""
    if node.infer_kind() == "combine":
        return {c for child in node.inputs() for c in _returned_classes(child, classes)}
    own = classes.get(node.search_name)
    return set() if own is None else {own.returns}


def transform_input_refusal(
    root: StrategyStepNode,
    classes: Mapping[str, SearchRecordClasses],
    record_names: Mapping[str, str],
) -> str | None:
    """Why the first transform whose input returns a record class it does not
    take is refused, or None. A search or an input of unknown class abstains."""
    for node in _nodes(root):
        own = classes.get(node.search_name)
        source = node.primary_input
        if node.infer_kind() != "transform" or source is None or own is None:
            continue
        given = sorted(_returned_classes(source, classes))
        if not own.takes or not given or set(given) <= set(own.takes):
            continue
        takes = " or ".join(record_names.get(c, c) for c in own.takes)
        if len(given) > 1:
            joined = " and ".join(record_names.get(c, c) for c in given)
            return (
                f"The subtree under {node.id} joins {joined} in one combine. WDK "
                f"combines only steps of one record class, so this tree cannot "
                f"run. Bind every input under {node.id} to a search on {takes}, "
                f"or ask the researcher."
            )
        returns = record_names.get(own.returns, own.returns)
        subtree = record_names.get(given[0], given[0])
        return (
            f"{node.id} runs {own.display_name} ({node.search_name}), which takes "
            f"{takes} as its input step, and the subtree under it returns "
            f"{subtree}. WDK runs a transform only on the record classes it "
            f"declares, so this tree cannot run. {own.display_name} maps {takes} "
            f"to {returns}; it is not a filter on {subtree}. Drop {node.id}, bind "
            f"it to a search on {subtree} that states it, or ask the researcher."
        )
    return None


@dataclass
class StepValidationIssue:
    """One issue found during validation."""

    path: str
    message: str
    code: str


@dataclass
class ValidationResult:
    """The outcome of a validation run."""

    valid: bool
    errors: list[StepValidationIssue]

    @classmethod
    def success(cls) -> ValidationResult:
        """Builds a successful result."""
        return cls(valid=True, errors=[])

    @classmethod
    def failure(cls, errors: list[StepValidationIssue]) -> ValidationResult:
        """Builds a failed result from the given issues."""
        return cls(valid=False, errors=errors)


class StrategyValidator:
    """Validates a strategy tree against the available searches and transforms."""

    def __init__(
        self,
        organism_params: Mapping[str, str],
        available_searches: dict[str, list[str]] | None = None,
        available_transforms: list[str] | None = None,
        *,
        dataset_organisms: Mapping[str, frozenset[str]] | None = None,
    ) -> None:
        """Builds a validator. Searches are keyed by record type, and
        ``dataset_organisms`` names the organisms of each search's dataset."""
        self.organism_params = organism_params
        self.available_searches = available_searches or {}
        self.available_transforms = available_transforms or []
        self.dataset_organisms = dataset_organisms or {}

    def validate(self, root: StrategyStepNode, record_type: str) -> ValidationResult:
        """Validates a strategy tree against a record type."""
        errors: list[StepValidationIssue] = []

        if not record_type:
            errors.append(
                StepValidationIssue(
                    path="recordType",
                    message="Record type is required",
                    code="MISSING_RECORD_TYPE",
                )
            )

        self._validate_node(root, root, "root", record_type, errors)

        return (
            ValidationResult.success()
            if not errors
            else ValidationResult.failure(errors)
        )

    def _validate_contrast_samples(
        self,
        node: StrategyStepNode,
        path: str,
        errors: list[StepValidationIssue],
    ) -> None:
        """Rejects a differential search that contrasts a group against itself.

        A reference and comparison name pair holds the two sides of the contrast. WDK
        runs an identical pair, so the check must happen here.
        """
        decoded = to_decoded_map(node.parameters)
        pairs: list[tuple[str, JsonValue, JsonValue]] = []
        for ref_name, ref_value in decoded.items():
            if "_ref_" not in ref_name:
                continue
            comp_value = decoded.get(ref_name.replace("_ref_", "_comp_"))
            if comp_value is not None:
                pairs.append((ref_name, ref_value, comp_value))
        percentile = decoded.get("samples_percentile_generic")
        comp = decoded.get("samples_fc_comp_generic")
        if percentile is not None and comp is not None:
            pairs.append(("samples_percentile_generic", percentile, comp))

        for param_name, ref_value, comp_value in pairs:
            if ref_value and comp_value and str(ref_value) == str(comp_value):
                errors.append(
                    StepValidationIssue(
                        path=f"{path}.parameters.{param_name}",
                        message=(
                            "Reference and comparison samples are identical "
                            f"({ref_value}) - this contrasts a group against "
                            "itself and produces meaningless differential "
                            "results. Set different samples for reference vs "
                            "comparison."
                        ),
                        code="IDENTICAL_CONTRAST_SAMPLES",
                    )
                )

    def _validate_cross_organism_intersect(
        self,
        node: StrategyStepNode,
        root: StrategyStepNode,
        path: str,
        errors: list[StepValidationIssue],
    ) -> None:
        """Rejects an INTERSECT between disjoint organism scopes."""
        message = cross_organism_refusal(
            node, root, self.organism_params, self.dataset_organisms
        )
        if message is None:
            return
        errors.append(
            StepValidationIssue(
                path=f"{path}.operator",
                message=message,
                code="CROSS_ORGANISM_INTERSECT",
            )
        )

    def _validate_combine_node(
        self,
        node: StrategyStepNode,
        path: str,
        errors: list[StepValidationIssue],
    ) -> None:
        """Validates the constraints that apply only to a combine node."""
        if node.operator is None:
            errors.append(
                StepValidationIssue(
                    path=f"{path}.operator",
                    message="operator is required for combine nodes",
                    code="MISSING_OPERATOR",
                )
            )
        elif node.operator not in CombineOp:
            errors.append(
                StepValidationIssue(
                    path=f"{path}.operator",
                    message=f"Invalid operator: {node.operator}",
                    code="INVALID_OPERATOR",
                )
            )
        if node.primary_input is None or node.secondary_input is None:
            errors.append(
                StepValidationIssue(
                    path=path,
                    message="Combine nodes require two inputs",
                    code="MISSING_INPUT",
                )
            )
        if node.operator == CombineOp.COLOCATE and node.colocation_params is None:
            errors.append(
                StepValidationIssue(
                    path=f"{path}.colocationParams",
                    message="colocationParams is required for COLOCATE",
                    code="MISSING_COLOCATION_PARAMS",
                )
            )

    def _validate_node(
        self,
        node: StrategyStepNode,
        root: StrategyStepNode,
        path: str,
        expected_record_type: str,
        errors: list[StepValidationIssue],
    ) -> None:
        """Validates one node and then its inputs."""
        if not node.search_name:
            errors.append(
                StepValidationIssue(
                    path=f"{path}.searchName",
                    message="searchName is required",
                    code="MISSING_SEARCH_NAME",
                )
            )

        if self.available_searches:
            rt_searches = self.available_searches.get(expected_record_type, [])
            if node.search_name and node.search_name not in rt_searches:
                errors.append(
                    StepValidationIssue(
                        path=f"{path}.searchName",
                        message=f"Unknown search: {node.search_name}",
                        code="UNKNOWN_SEARCH",
                    )
                )

        self._validate_contrast_samples(node, path, errors)

        if node.infer_kind() == "combine":
            self._validate_combine_node(node, path, errors)
            self._validate_cross_organism_intersect(node, root, path, errors)

        if node.secondary_input is not None:
            self._validate_node(
                node.secondary_input,
                root,
                f"{path}.secondaryInput",
                expected_record_type,
                errors,
            )
        if node.primary_input is not None:
            self._validate_node(
                node.primary_input,
                root,
                f"{path}.primaryInput",
                expected_record_type,
                errors,
            )


def validate_strategy(
    root: StrategyStepNode,
    record_type: str,
    organism_params: Mapping[str, str],
    dataset_organisms: Mapping[str, frozenset[str]] | None = None,
) -> ValidationResult:
    """Validates a strategy tree with the default validator."""
    validator = StrategyValidator(organism_params, dataset_organisms=dataset_organisms)
    return validator.validate(root, record_type)
