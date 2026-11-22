from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, ParamValue, StringValue

from strategist.domain.strategy.readings import AcceptedReading

_STAGES: dict[str, ParamValue] = {
    "stages": MultiPickValue(values=["trophozoite", "schizont"])
}


def _reading(wire: str) -> AcceptedReading:
    return AcceptedReading(reading="blood stages", params={"stages": wire})


def test_a_reading_restated_in_another_order_is_the_same_reading() -> None:
    held = _reading('["trophozoite","schizont"]')

    assert held.same_reading(_reading('["schizont", "trophozoite"]'), _STAGES)


def test_a_reading_with_another_pick_is_another_reading() -> None:
    held = _reading('["trophozoite","schizont"]')

    assert not held.same_reading(_reading('["trophozoite"]'), _STAGES)


def test_a_text_parameter_reads_two_spellings_apart() -> None:
    text: dict[str, ParamValue] = {"stages": StringValue(value="1")}

    assert not _reading("1").same_reading(_reading("1.0"), text)
