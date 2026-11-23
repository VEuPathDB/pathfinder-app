import strategist_scripted
from strategist.ai.scripted import scripted


def test_the_seam_answers_the_scripted_package_record() -> None:
    assert scripted() is strategist_scripted.SCRIPTED
