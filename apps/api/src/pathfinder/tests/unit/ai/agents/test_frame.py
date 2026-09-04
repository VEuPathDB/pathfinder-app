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
    assert "the parameter sheet in `decide`" in _FRAME_INSTRUCTIONS
    assert "get_search_overview" not in _FRAME_INSTRUCTIONS
    assert "redecide" in _FRAME_INSTRUCTIONS


def test_frame_instructions_name_the_params_template() -> None:
    # The instruction hands the model the object to copy, so no parameter name
    # has to be composed.
    assert (
        "The result's `params_template` is the exact `params` object to send back: "
        "copy it and replace each null with a value or leave null; do not rename keys."
    ) in _normalized(_FRAME_INSTRUCTIONS)


def test_frame_instructions_ask_for_the_sheet_once() -> None:
    # A repeat sheet costs its vocabularies again and states nothing new.
    assert "ONCE per criterion" in _normalized(_FRAME_INSTRUCTIONS)
    assert "vocabularies stripped" in _FRAME_INSTRUCTIONS


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
        "half; a wildcard you would have typed is a "
        "`get_parameter_options(query=...)` over the vocabulary, then every entry "
        "it covers. The halves are ORed, so a value in both widens the search, and "
        "the vocabulary half cannot be switched off"
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
    # The sheet has to be the tool result immediately before the proposal, so
    # the procedure asks for it with a params-less `set_criterion` call.
    assert "no `params`" in _FRAME_INSTRUCTIONS
    assert "returns the parameter sheet" in _FRAME_INSTRUCTIONS


def test_get_parameter_options_is_only_the_shortlist_escape_hatch() -> None:
    # Parameter names come from the sheet alone; both mentions answer "the
    # entries I need are not shown", once for a shortlist and once for the
    # entries a wildcard would have covered.
    assert _FRAME_INSTRUCTIONS.count("get_parameter_options") == 2
    assert "never to discover parameter names" in _FRAME_INSTRUCTIONS


def test_frame_instructions_select_every_matching_sample() -> None:
    # A named sample class is answered from the sheet, not turned into a
    # question the user already answered.
    assert "SELECT every matching sample" in _normalized(_FRAME_INSTRUCTIONS)
    assert "Only when nothing on the sheet matches do you ask the user" in (
        _FRAME_INSTRUCTIONS
    )


def test_frame_instructions_say_when_to_declare_an_assumption() -> None:
    # A value the request does not state is recorded as a constraint the user
    # can override, rather than being narrated once and lost.
    assert (
        "Assumed values: when you choose a value the criterion text does not "
        "state and that is not the sheet's default, declare it in `assumed` "
        "with the parameter name, the value and one sentence of reason. Each "
        "becomes a constraint the user reads and can override. A value the "
        'request states is not an assumption: "top 10 percent" states the '
        "minimum percentile 90. A half of a reference and comparison pair is "
        "never assumed - state the group the request names, or leave it null "
        "and ask."
    ) in _normalized(_FRAME_INSTRUCTIONS)


def test_frame_instructions_send_the_model_to_a_past_case_before_binding() -> None:
    # A verified run leaves a case; nothing reads it unless the procedure says so.
    assert (
        'Before step 1, read what already worked: `search_memory(query, kind="case")` '
        "returns cases from this user's verified runs - each names the searches, the "
        "params and the count that landed - and `search_example_plans(query)` returns "
        "public VEuPathDB strategies ranked against the goal. Both are reading; "
        "neither binds a criterion."
    ) in _normalized(_FRAME_INSTRUCTIONS)
