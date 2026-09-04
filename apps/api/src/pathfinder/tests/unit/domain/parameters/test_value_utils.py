import pytest

from pathfinder.domain.parameters._value_helpers import (
    SinglePickProcessed,
    process_single_pick,
)
from pathfinder.domain.parameters.specs import ParamSpecNormalized
from pathfinder.domain.parameters.value_utils import decode_single_value
from pathfinder.domain.parameters.wdk_vocab import WDKVocabTerm
from pathfinder.platform.errors import ValidationError


def test_comma_containing_value_is_one_value() -> None:
    value = "P. falciparum 3D7 asexual stages, salivary gland sporozoite"
    assert decode_single_value(value, "profileset_generic") == [value]


def test_explicit_json_array_string_is_multiple() -> None:
    assert decode_single_value('["A", "B"]', "x") == ["A", "B"]


def test_list_input_is_multiple() -> None:
    assert decode_single_value(["A", "B"], "x") == ["A", "B"]


def test_plain_value_is_one() -> None:
    assert decode_single_value("Gametocyte V", "x") == ["Gametocyte V"]


def test_empty_is_no_values() -> None:
    assert decode_single_value("", "x") == []


def test_process_single_pick_accepts_comma_containing_vocab_value() -> None:
    value = "P. falciparum 3D7 asexual stages, salivary gland sporozoite"
    spec = ParamSpecNormalized(
        name="profileset_generic",
        param_type="single-pick-vocabulary",
        vocabulary=[WDKVocabTerm((value, value, None))],
    )
    out = process_single_pick(spec, value)
    assert isinstance(out, SinglePickProcessed)
    assert out.value == value


def test_process_single_pick_rejects_genuine_multiple() -> None:
    spec = ParamSpecNormalized(
        name="profileset_generic",
        param_type="single-pick-vocabulary",
        vocabulary=[
            WDKVocabTerm(("A", "A", None)),
            WDKVocabTerm(("B", "B", None)),
        ],
    )
    with pytest.raises(ValidationError, match="only one value"):
        process_single_pick(spec, ["A", "B"])
