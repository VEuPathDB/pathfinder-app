"""Validates a strategy tree and reports the issues it finds."""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from pydantic import JsonValue
from veupathdb.domain.parameters import to_decoded_map
from veupathdb.domain.strategy import CombineOp, StrategyStepNode

from pathfinder.domain.strategy.organism_remedy import remedy_for, scope_text
from pathfinder.domain.strategy.organism_scope import (
    NO_TAXA,
    organisms_of,
    output_organisms,
)


def cross_organism_refusal(
    combine: StrategyStepNode,
    root: StrategyStepNode,
    organism_params: Mapping[str, str],
    dataset_organisms: Mapping[str, frozenset[str]],
    *,
    taxa: Mapping[str, frozenset[str]] = NO_TAXA,
) -> str | None:
    """Why the combine returns nothing, or None when its inputs can meet.

    Gene ids from different organisms never match, so an INTERSECT of two known
    and disjoint scopes is always empty. A search reads its organism from the
    parameter it marks, or from its dataset when it marks none. ``taxa`` gives
    the organisms under each entry of the organism tree that holds some.
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
    if primary is None or secondary is None:
        return None
    if not organisms_of(primary, taxa).isdisjoint(organisms_of(secondary, taxa)):
        return None
    remedy = remedy_for(
        root, combine, (primary, secondary), organism_params, dataset_organisms
    )
    return (
        f"Cannot INTERSECT steps with different organism scopes "
        f"({scope_text(primary)} vs {scope_text(secondary)}). Gene IDs from "
        f"different organisms never match, so this always returns 0 results. "
        f"{remedy}"
    )


def first_cross_organism_refusal(
    root: StrategyStepNode,
    organism_params: Mapping[str, str],
    dataset_organisms: Mapping[str, frozenset[str]],
    *,
    taxa: Mapping[str, frozenset[str]] = NO_TAXA,
) -> str | None:
    """Why the first INTERSECT of the tree that can never meet is refused, or None."""
    for node in _nodes(root):
        refusal = cross_organism_refusal(
            node, root, organism_params, dataset_organisms, taxa=taxa
        )
        if refusal is not None:
            return refusal
    return None


def _nodes(node: StrategyStepNode) -> Iterator[StrategyStepNode]:
    yield node
    for child in node.inputs():
        yield from _nodes(child)


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
        taxa: Mapping[str, frozenset[str]] = NO_TAXA,
    ) -> None:
        """Builds a validator. Searches are keyed by record type,
        ``dataset_organisms`` names the organisms of each step's dataset by step
        id, and ``taxa`` the organisms under each entry of the organism tree."""
        self.organism_params = organism_params
        self.available_searches = available_searches or {}
        self.available_transforms = available_transforms or []
        self.dataset_organisms = dataset_organisms or {}
        self.taxa = taxa

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
            node, root, self.organism_params, self.dataset_organisms, taxa=self.taxa
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
    *,
    taxa: Mapping[str, frozenset[str]] = NO_TAXA,
) -> ValidationResult:
    """Validates a strategy tree with the default validator."""
    validator = StrategyValidator(
        organism_params, dataset_organisms=dataset_organisms, taxa=taxa
    )
    return validator.validate(root, record_type)
