"""FRAME's procedure states the parameter-sheet contract it works under."""

from __future__ import annotations

from pathfinder.ai.agents.frame import _FRAME_INSTRUCTIONS


def _normalized(text: str) -> str:
    """The instructions wrap, so a phrase is asserted without its line breaks."""
    return " ".join(text.split())


def test_frame_instructions_describe_the_contract() -> None:
    assert "params" in _FRAME_INSTRUCTIONS
    assert "param_overrides" not in _FRAME_INSTRUCTIONS
    assert "organism_scope" not in _FRAME_INSTRUCTIONS


def test_frame_instructions_name_the_sheet_and_the_redecide_round_trip() -> None:
    # The flow is search -> sheet -> params. `search_for_searches` already
    # returns the description, so nothing sends the model to the overview tool.
    assert "OPENS the parameter sheet" in _FRAME_INSTRUCTIONS
    assert "get_search_overview" not in _FRAME_INSTRUCTIONS
    assert "redecide" in _FRAME_INSTRUCTIONS


def test_frame_instructions_name_the_params_template() -> None:
    # The instruction hands the model the object to copy, so no parameter name
    # has to be composed.
    assert (
        "Its `params_template` is the exact `params` object to send back: "
        "copy it and replace each null with a value or leave null; do not rename keys."
    ) in _normalized(_FRAME_INSTRUCTIONS)


def test_frame_instructions_ask_for_the_sheet_once() -> None:
    # The sheet is pinned until the criterion binds, so a repeat states nothing new.
    assert "ONCE per criterion" in _normalized(_FRAME_INSTRUCTIONS)
    assert "it stays pinned" in _normalized(_FRAME_INSTRUCTIONS)


def test_frame_instructions_drop_the_rules_that_no_longer_exist() -> None:
    # Numbers, lists and JSON strings are read as typed; a direction is one
    # more vocabulary value on the sheet, not a tool argument.
    assert "overrides are strings" not in _FRAME_INSTRUCTIONS
    assert "direction" not in _FRAME_INSTRUCTIONS


def test_frame_instructions_ask_for_every_value_a_multi_pick_covers() -> None:
    # One representative sample out of the three the criterion names is a
    # different question, and it is invisible in the bound value.
    assert "EVERY value the criterion covers" in _FRAME_INSTRUCTIONS
    assert "never one" in _FRAME_INSTRUCTIONS


def test_frame_instructions_keep_the_structure_rules() -> None:
    assert "transform" in _FRAME_INSTRUCTIONS
    assert "INTERSECT" in _FRAME_INSTRUCTIONS
    assert "UNION" in _FRAME_INSTRUCTIONS


def test_frame_instructions_fill_the_vocabulary_half_of_a_radio_pair() -> None:
    # The two halves are ORed, so a filled free-text half widens the search.
    # `N/A` is the value those searches accept as unused; an empty string is
    # refused. A wildcard is a vocabulary read, not a value to type.
    assert (
        "the vocabulary half carries the criterion; pass `N/A` for the free-text "
        "half. The halves are ORed, so a value in both widens the search, and the "
        "vocabulary half cannot be switched off"
    ) in _normalized(_FRAME_INSTRUCTIONS)


def test_frame_instructions_read_a_typeahead_vocabulary_before_binding_it() -> None:
    assert (
        "A typeahead vocabulary (GO term, InterPro domain, EC number) is always read "
        "this way before you bind it: the sheet's list is ranked by name and is not "
        "the concept, so `set_criterion` refuses a new entry on it that no lookup of "
        "this pass matched, unless the request writes the entry out"
    ) in _normalized(_FRAME_INSTRUCTIONS)


def test_frame_instructions_state_the_two_species_lists() -> None:
    # The pattern is hidden and required, so a criterion stated anywhere else
    # binds the published default and the search returns no genes.
    assert (
        "for a phylogenetic-profile search, name the species or clades that must "
        "have an ortholog in `included_species` and those that must not in "
        "`excluded_species` (codes or labels from the sheet; a clade selects all "
        "its species; `lookup_phyletic_codes(query)` finds a code from a common "
        "name); the hidden `profile_pattern` is derived from those two lists, "
        "never write it"
    ) in _normalized(_FRAME_INSTRUCTIONS)


def test_frame_instructions_re_resolve_a_substitutions_dependents() -> None:
    # A dependent value names an entry of the OLD parent's vocabulary, so
    # copying it forward binds a value the new parent does not offer.
    assert (
        "A parameter that hangs off the one the request changes is not copied: "
        "answer each `redecide` entry from the fresh vocabulary it comes back "
        "with, and never null a parameter the previous binding held unless the "
        "request removes it."
    ) in _normalized(_FRAME_INSTRUCTIONS)


def test_frame_instructions_are_ascii() -> None:
    assert _FRAME_INSTRUCTIONS.isascii()


def test_frame_instructions_get_the_sheet_from_set_criterion() -> None:
    # The sheet is pinned by a params-less `set_criterion` call and read from
    # the instructions, so the procedure names both halves.
    assert "no `params`" in _FRAME_INSTRUCTIONS
    assert "Open parameter sheets" in _FRAME_INSTRUCTIONS


def test_get_parameter_options_is_only_the_shortlist_escape_hatch() -> None:
    # Parameter names come from the sheet alone; both mentions answer "the
    # entries I need are not shown", once for a shortlist and once for the
    # entries a wildcard would have covered.
    assert _FRAME_INSTRUCTIONS.count("get_parameter_options") == 2
    assert "never to discover parameter names" in _FRAME_INSTRUCTIONS


def test_frame_instructions_say_the_tool_records_who_set_each_value() -> None:
    # The tool decides the source of a value, so the model states the reason.
    assert (
        "Chosen values: the tool records who set each value. A value whose "
        "words the researcher's messages hold is theirs, the sheet's default "
        "is the site's, and every other value is your choice, recorded with "
        "the reason you give in `why`."
    ) in _normalized(_FRAME_INSTRUCTIONS)


def test_frame_instructions_bind_only_a_search_that_states_the_criterion() -> None:
    text = _normalized(_FRAME_INSTRUCTIONS)

    assert ("Bind a search only if its summary states what the criterion asks.") in text
    assert 'do not bind the nearest one: set disposition="needs_user"' in text


def test_frame_instructions_say_another_sites_experiment_never_binds() -> None:
    assert (
        "Its last entry may be `otherSites`: experiments on other VEuPathDB sites, "
        "each labelled with its site. They inform and never bind: none is a search "
        "on this site. To use one, `read_experiment(dataset_id)` answers its card, "
        "whose record URL and PMIDs you may cite in `why.sources`; then search this "
        "site for its condition, stage or organism."
    ) in _normalized(_FRAME_INSTRUCTIONS)


def test_frame_offers_the_orthologs_when_two_organisms_cannot_intersect() -> None:
    # Gene ids of two species never match, so the refused INTERSECT is answered
    # with the transform that carries one set into the other organism.
    assert (
        "An INTERSECT of genes of two organisms is refused by `set_structure`: "
        "gene ids of two species never match. Do not re-scope the request to one "
        'organism: set disposition="needs_user" and ask whether to carry one set '
        'to its orthologs in the other organism, with dimension "organism" and '
        "that transform as the recommended value."
    ) in _normalized(_FRAME_INSTRUCTIONS)


def test_frame_instructions_keep_the_organism_a_value() -> None:
    assert (
        "The organism the request names is a value of each search's organism "
        "parameter, never a criterion of its own."
    ) in _normalized(_FRAME_INSTRUCTIONS)
