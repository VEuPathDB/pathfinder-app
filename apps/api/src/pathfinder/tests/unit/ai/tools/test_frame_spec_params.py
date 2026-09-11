"""How ``set_criterion`` decides a parameter: resolution, defaults, redecide."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters.value_codec import to_wire
from veupathdb.domain.parameters.wdk_vocab import VocabOption
from veupathdb_mcp.catalog import (
    ParameterInfo,
    fetch_search_details,
    param_discovery,
)

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone.frame_spec import SetCriterionResult
from pathfinder.tests.unit.ai.tools.test_frame_proposals import (
    PHYLETIC_ORGANISM,
    propose,
    serve_for,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    KINASE_PARAMS,
    Proposals,
    bind,
    genes_by_text,
    param_info,
    serve_search,
)

_AVERAGE_ONLY = [VocabOption(value="average1", display="average")]
_EVERY_AGGREGATION = [
    VocabOption(value="average1", display="average"),
    VocabOption(value="minimum2", display="minimum"),
    VocabOption(value="maximum2", display="maximum"),
]
_AGGREGATION_TEXT = "aggregate expression over the sampled patients"


def _aggregation_under_samples(context: dict[str, str]) -> list[ParameterInfo]:
    """The child's vocabulary opens up only once the samples are bound."""
    bound = "samples_generic" in context
    return [
        param_info(
            "samples_generic",
            "multi-pick-vocabulary",
            vocab_leaves=[VocabOption(value="sampleA", display="sampleA")],
        ),
        param_info(
            "min_max_avg_ref",
            "single-pick-vocabulary",
            vocab_leaves=_EVERY_AGGREGATION if bound else _AVERAGE_ONLY,
            default_value="average1",
            vocab_depends_on=["samples_generic"],
        ),
    ]


async def _aggregate(
    state: AgentToolState,
    aggregation: str | None,
    *,
    criterion_id: str = "c1",
    search_name: str = "GenesByRNASeq",
) -> SetCriterionResult:
    return await bind(
        state,
        search_name,
        {"samples_generic": ["sampleA"], "min_max_avg_ref": aggregation},
        criterion_id=criterion_id,
        text=_AGGREGATION_TEXT,
    )


class TestADependentVocabularyIsRedecided:
    @pytest.mark.asyncio
    async def test_a_changed_vocabulary_comes_back_to_be_decided(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_search(monkeypatch, _aggregation_under_samples)
        st = AgentToolState()

        result = await _aggregate(st, None)

        assert [entry.name for entry in result.redecide] == ["min_max_avg_ref"]
        fresh = [option.value for option in result.redecide[0].vocabulary]
        assert fresh == ["average1", "minimum2", "maximum2"]
        assert st.operational_spec_draft.criteria == [], "nothing is recorded yet"

    @pytest.mark.asyncio
    async def test_a_value_from_the_fresh_vocabulary_binds_as_stated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_search(monkeypatch, _aggregation_under_samples)
        st = AgentToolState()

        result = await _aggregate(st, "minimum2")

        assert result.redecide == []
        assert result.resolved_params["min_max_avg_ref"] == "minimum2"
        assert "min_max_avg_ref" not in result.defaulted_params
        assert st.operational_spec_draft.criteria[0].id == "c1"

    @pytest.mark.asyncio
    async def test_an_unchanged_vocabulary_is_not_redecided(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_search(monkeypatch, genes_by_text)

        result = await bind(AgentToolState(), "GenesByText", dict(KINASE_PARAMS))

        assert result.redecide == []


class TestARedecidedParamIsDecidedOnce:
    """The re-call closes the question, whichever way the model answers it.

    A ``redecide`` is a successful return, so no retry budget bounds it, and
    asking again leaves the criterion unbound for the whole turn.
    """

    @pytest.mark.asyncio
    async def test_the_same_null_binds_the_default_under_the_bound_parents(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_search(monkeypatch, _aggregation_under_samples)
        st = AgentToolState()

        first = await _aggregate(st, None)
        second = await _aggregate(st, None)

        assert [entry.name for entry in first.redecide] == ["min_max_avg_ref"]
        assert second.redecide == []
        assert second.resolved_params["min_max_avg_ref"] == "average1"
        assert "min_max_avg_ref" in second.defaulted_params
        assert st.operational_spec_draft.criteria[0].id == "c1"

    @pytest.mark.asyncio
    async def test_a_fresh_value_on_the_re_call_binds_as_stated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_search(monkeypatch, _aggregation_under_samples)
        st = AgentToolState()

        await _aggregate(st, None)
        second = await _aggregate(st, "minimum2")

        assert second.redecide == []
        assert second.resolved_params["min_max_avg_ref"] == "minimum2"
        assert "min_max_avg_ref" not in second.defaulted_params

    @pytest.mark.asyncio
    async def test_a_value_outside_the_fresh_vocabulary_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_search(monkeypatch, _aggregation_under_samples)
        st = AgentToolState()

        await _aggregate(st, None)
        with pytest.raises(ModelRetry) as info:
            await _aggregate(st, "median9")

        message = str(info.value)
        assert "min_max_avg_ref" in message
        assert "minimum2" in message
        assert st.operational_spec_draft.criteria == []

    @pytest.mark.asyncio
    async def test_the_ledger_is_kept_per_criterion(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Two criteria over the same search are two separate questions.
        serve_search(monkeypatch, _aggregation_under_samples)
        st = AgentToolState()

        await _aggregate(st, None)
        other = await _aggregate(st, None, criterion_id="c2")

        assert [entry.name for entry in other.redecide] == ["min_max_avg_ref"]

    @pytest.mark.asyncio
    async def test_the_ledger_is_kept_per_search(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Searches share parameter names. Re-pointing a criterion at another
        # search asks the question again, over that search's own vocabulary.
        serve_search(monkeypatch, _aggregation_under_samples)
        st = AgentToolState()

        await _aggregate(st, None)
        elsewhere = await _aggregate(st, None, search_name="GenesByRNASeqAlternative")

        assert [entry.name for entry in elsewhere.redecide] == ["min_max_avg_ref"]


@pytest.mark.asyncio
async def test_the_default_context_is_fetched_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The name check, the DAG's first pass and the redecide baseline all want
    # the same expandParams payload.
    seen: list[dict[str, str]] = []

    def _counted(context: dict[str, str]) -> list[ParameterInfo]:
        seen.append(dict(context))
        return _aggregation_under_samples(context)

    serve_search(monkeypatch, _counted)

    await _aggregate(AgentToolState(), None)

    assert [c for c in seen if not c] == [{}]


_PF = "Plasmodium falciparum 3D7"
_PV = "Plasmodium vivax P01"
_DERISI_SET = "DeRisi 3D7 Smoothed"
_ZHU = "Zhu P01 time course"


def _profilesets_under_organism(context: dict[str, str]) -> list[ParameterInfo]:
    organism = param_info(
        "organism",
        "multi-pick-vocabulary",
        vocab_leaves=[
            VocabOption(value=_PF, display="P. falciparum 3D7"),
            VocabOption(value=_PV, display="P. vivax P01"),
        ],
    )
    under_vivax = _PV in context.get("organism", "")
    allowed = (
        [VocabOption(value=_ZHU, display="Zhu P01")]
        if under_vivax
        else [
            VocabOption(value=_DERISI_SET, display=_DERISI_SET),
            VocabOption(value="Su 3D7 strand-specific", display="Su 3D7"),
        ]
    )
    return [
        organism,
        param_info(
            "profileset",
            "single-pick-vocabulary",
            default_value=_ZHU if under_vivax else _DERISI_SET,
            allowed_values=allowed,
            vocab_depends_on=["organism"],
        ),
    ]


async def _profile(state: AgentToolState, params: Proposals) -> SetCriterionResult:
    return await bind(
        state,
        "GenesByProfile",
        params,
        criterion_id="step_expr",
        text="expression profile of the protease genes",
    )


class TestAnOrganismSwapRedecidesItsDependents:
    """A dependent value names an entry of the OLD organism's vocabulary, so
    re-binding with a new organism hands the dependent back to be decided."""

    @pytest.fixture(autouse=True)
    def _serve(self, monkeypatch: pytest.MonkeyPatch) -> None:
        serve_search(monkeypatch, _profilesets_under_organism)
        monkeypatch.setattr(
            param_discovery, "fetch_search_details", fetch_search_details
        )

    @pytest.mark.asyncio
    async def test_the_swap_hands_back_the_dependent_it_invalidated(self) -> None:
        state = AgentToolState()

        result = await _profile(state, {"organism": [_PV], "profileset": _DERISI_SET})

        assert [entry.name for entry in result.redecide] == ["profileset"]
        assert [o.value for o in result.redecide[0].vocabulary] == [_ZHU]
        assert state.operational_spec_draft.criteria == [], "nothing is recorded yet"

    @pytest.mark.asyncio
    async def test_the_fresh_value_binds_and_the_other_params_are_copied(self) -> None:
        state = AgentToolState()

        await _profile(state, {"organism": [_PV], "profileset": _DERISI_SET})
        result = await _profile(state, {"organism": [_PV], "profileset": _ZHU})

        assert result.redecide == []
        assert result.resolved_params["profileset"] == _ZHU
        assert result.resolved_params["organism"] == f'["{_PV}"]'
        assert state.operational_spec_draft.criteria[0].id == "step_expr"

    @pytest.mark.asyncio
    async def test_the_old_organisms_value_is_refused_on_the_re_call(self) -> None:
        """A second pass that copies the stale value forward is a retry."""
        state = AgentToolState()

        await _profile(state, {"organism": [_PV], "profileset": _DERISI_SET})
        with pytest.raises(ModelRetry) as excinfo:
            await _profile(state, {"organism": [_PV], "profileset": _DERISI_SET})

        message = str(excinfo.value)
        assert "profileset" in message
        assert _ZHU in message
        assert state.operational_spec_draft.criteria == []

    @pytest.mark.asyncio
    async def test_an_unchanged_organism_re_binds_without_a_redecide(self) -> None:
        """Re-stating the same values changes nothing and asks nothing."""
        state = AgentToolState()

        result = await _profile(state, {"organism": [_PF], "profileset": _DERISI_SET})

        assert result.redecide == []
        assert result.resolved_params["profileset"] == _DERISI_SET


_LABELLED = {**KINASE_PARAMS, "text_search_organism": ["P. falciparum 3D7"]}
_BINDINGS: list[tuple[str, Proposals, dict[str, str]]] = [
    (
        "GenesByText",
        _LABELLED,
        {"text_search_organism": '["Plasmodium falciparum 3D7"]'},
    ),
    (
        "GenesByInterproDomain",
        {"domain_typeahead": "PF00069"},
        {"domain_typeahead": "PF00069 : Pkinase"},
    ),
    (
        "GenesByOrthologPattern",
        {
            **PHYLETIC_ORGANISM,
            "included_species": "pfal",
            "excluded_species": "Mammalia",
        },
        {
            "profile_pattern": "%hsap:N%mmus:N%pfal:Y%",
            "included_species": "pfal",
            "excluded_species": "MAMM",
        },
    ),
    (
        "GenesByOrthologPattern",
        {
            **PHYLETIC_ORGANISM,
            "included_species": "Plasmodium falciparum 3D7",
            "excluded_species": ["Homo sapiens REF"],
        },
        {"profile_pattern": "%hsap:N%pfal:Y%", "included_species": "pfal"},
    ),
    # The canonical lists are comma-joined codes, which name no single entry.
    (
        "GenesByOrthologPattern",
        {**PHYLETIC_ORGANISM, "excluded_species": "hsap, mmus"},
        {"excluded_species": "hsap, mmus", "profile_pattern": "%hsap:N%mmus:N%"},
    ),
    (
        "GenesByEcNumber",
        {"ec_number_pattern": "2.7.-.-", "ec_wildcard": None},
        {"ec_number_pattern": "2.7.-.-", "ec_wildcard": "N/A"},
    ),
]


@pytest.mark.parametrize(("search", "params", "expected"), _BINDINGS)
@pytest.mark.asyncio
async def test_a_proposal_binds_the_value_the_vocabulary_names(
    monkeypatch: pytest.MonkeyPatch,
    search: str,
    params: Proposals,
    expected: dict[str, str],
) -> None:
    serve_for(monkeypatch, search)

    result = await propose(AgentToolState(), search, params)

    assert {name: result.resolved_params[name] for name in expected} == expected


@pytest.mark.asyncio
async def test_the_stated_value_binds_and_is_not_a_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_for(monkeypatch, "GenesByExpressionPercentile")
    st = AgentToolState()

    result = await propose(
        st, "GenesByExpressionPercentile", {"min_expression_percentile": "90"}
    )

    assert result.resolved_params == {"min_expression_percentile": "90"}
    assert result.defaulted_params == []
    assert st.operational_spec_draft.criteria[0].id == "c1"


@pytest.mark.asyncio
async def test_a_criterion_stating_no_quantity_keeps_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Binding the search default under a stated number would report WDK's own
    # threshold as the researcher's; with none stated the default is right.
    serve_for(monkeypatch, "GenesByExpressionPercentile")

    result = await bind(
        AgentToolState(),
        "GenesByExpressionPercentile",
        {"min_expression_percentile": None},
        text="highly expressed genes",
    )

    assert result.resolved_params == {"min_expression_percentile": "80"}
    assert result.defaulted_params == ["min_expression_percentile"]


@pytest.mark.asyncio
async def test_the_off_value_of_a_radio_pair_opens_no_slot_and_is_disclosed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_for(monkeypatch, "GenesByEcNumber")

    result = await propose(
        AgentToolState(),
        "GenesByEcNumber",
        {"ec_number_pattern": "2.7.-.-", "ec_wildcard": None},
    )

    assert result.open_slots == []
    assert "ec_wildcard" in result.defaulted_params


@pytest.mark.asyncio
async def test_a_search_declaring_no_radio_pair_is_unaffected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_for(monkeypatch, "GenesByText")

    result = await propose(AgentToolState(), "GenesByText", dict(KINASE_PARAMS))

    assert "N/A" not in result.resolved_params.values()


@pytest.mark.asyncio
async def test_the_derived_pattern_is_stated_and_is_no_open_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `profile_pattern` is hidden and required, so a call that does not derive
    # it binds the published default, which matches no census.
    serve_for(monkeypatch, "GenesByOrthologPattern")
    st = AgentToolState()

    result = await propose(
        st,
        "GenesByOrthologPattern",
        {**PHYLETIC_ORGANISM, "included_species": "pfal"},
    )

    assert result.open_slots == []
    assert "profile_pattern" not in result.defaulted_params
    criterion = st.operational_spec_draft.criteria[0]
    assert to_wire(criterion.resolved_params["profile_pattern"]) == "%pfal:Y%"


@pytest.mark.asyncio
async def test_the_derivation_reads_the_search_through_the_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The catalog memoizes the definition per record type and search.
    read = serve_for(monkeypatch, "GenesByOrthologPattern")

    await propose(
        AgentToolState(),
        "GenesByOrthologPattern",
        {**PHYLETIC_ORGANISM, "included_species": "pfal"},
    )

    assert [(c.record_type, c.search_name) for c in read] == [
        ("transcript", "GenesByOrthologPattern")
    ]
