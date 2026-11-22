"""The snapshot is a projection of the library's parameter model."""

from __future__ import annotations

from veupathdb.domain.parameters import HeldValue, VocabOption, shown_stated
from veupathdb_mcp.catalog import ParameterInfo

from strategist.ai.agents.param_vocab_render import render_param_vocab
from strategist.ai.agents.state import ParamVocabSnapshot
from strategist.tests._support.param_infos import sheet_of
from strategist.tests._support.recorded_searches import suite_search


def _info() -> ParameterInfo:
    return ParameterInfo(
        name="hard_floor",
        display_name="Tier floor",
        type="number-enum",
        required=True,
        is_visible=True,
        site_set=False,
        help="Tier-quantile floor for read counts",
        default="6772.93",
        allowed_values=[
            VocabOption(value="1693.23", display="1693 reads"),
            VocabOption(value="6772.93", display="6772 reads"),
        ],
    )


def test_the_snapshot_reads_the_library_parameter() -> None:
    snapshot = ParamVocabSnapshot.model_validate(_info(), from_attributes=True)

    assert snapshot.param_type == "number-enum"
    assert snapshot.required is True
    assert snapshot.help == "Tier-quantile floor for read counts"
    assert snapshot.default == "6772.93"
    assert snapshot.allowed_values == [
        VocabOption(value="1693.23", display="1693 reads"),
        VocabOption(value="6772.93", display="6772 reads"),
    ]
    assert snapshot.allowed_values_tree is None


def test_the_snapshot_still_takes_its_own_field_name() -> None:
    """The prompts read ``param_type``, so the alias keeps both names."""
    snapshot = ParamVocabSnapshot(param_type="string", required=False)

    assert snapshot.param_type == "string"


def test_the_default_is_rendered_as_it_is_stated() -> None:
    snapshot = ParamVocabSnapshot.model_validate(
        _info().model_copy(update={"default": ["Plasmodium falciparum 3D7"]}),
        from_attributes=True,
    )

    [head, *_] = render_param_vocab("organism", snapshot)

    assert head.endswith('default=["Plasmodium falciparum 3D7"]')


def _sample_meta() -> ParameterInfo:
    snps = suite_search("search_genes_by_ngs_snps")
    [meta] = [
        i for i in sheet_of(snps.parameters or []) if i.name == "variation_sample_meta"
    ]
    return meta


def test_a_filter_with_no_clause_defaults_to_its_stated_form() -> None:
    snapshot = ParamVocabSnapshot.model_validate(_sample_meta(), from_attributes=True)

    [head, *_] = render_param_vocab("variation_sample_meta", snapshot)

    assert head.endswith("default=[]")


def test_a_kept_default_is_rendered_unescaped() -> None:
    kept = _sample_meta().model_copy(
        update={"default": shown_stated(HeldValue(wire="a,b"))}
    )
    snapshot = ParamVocabSnapshot.model_validate(kept, from_attributes=True)

    [head, *_] = render_param_vocab("variation_sample_meta", snapshot)

    assert head.endswith("default='a,b' (kept as the site holds it)")
