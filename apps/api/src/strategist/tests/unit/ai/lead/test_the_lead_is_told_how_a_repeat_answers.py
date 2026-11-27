from strategist.ai.lead._lead_instructions import LEAD_GENE_RECORD_RULE


def test_the_record_rule_states_how_a_repeat_answers() -> None:
    assert LEAD_GENE_RECORD_RULE.endswith(
        "A read sent again with the same arguments runs nothing and costs nothing: "
        "while its answer is still shown, the reply names the call that answered "
        "it, and once that answer is no longer shown, the reply carries it again."
    )
