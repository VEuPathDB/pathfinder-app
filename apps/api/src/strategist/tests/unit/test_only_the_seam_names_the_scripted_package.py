from pathlib import Path

import strategist

_ROOT = Path(strategist.__file__).parent


def test_only_the_config_names_the_scripted_package() -> None:
    naming = sorted(
        source.relative_to(_ROOT).as_posix()
        for source in _ROOT.rglob("*.py")
        if not source.is_relative_to(_ROOT / "tests")
        and "strategist_scripted" in source.read_text()
    )

    assert naming == ["platform/config.py"]
