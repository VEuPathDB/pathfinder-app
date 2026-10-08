"""Every source an image copies from the build context is in a clean checkout."""

import fnmatch

import pytest

from pathfinder.platform.paths import REPO_ROOT

_DOCKERFILES = ("apps/api/Dockerfile", "apps/web/Dockerfile")


def _context_sources(dockerfile: str) -> list[str]:
    text = (REPO_ROOT / dockerfile).read_text().replace("\\\n", " ")
    sources: list[str] = []
    for line in text.splitlines():
        words = line.split()
        if words[:1] != ["COPY"] or any(w.startswith("--from=") for w in words):
            continue
        paths = [word for word in words[1:] if not word.startswith("--")]
        sources.extend(paths[:-1])
    return sources


def _ignore_rules() -> list[str]:
    lines = (REPO_ROOT / ".gitignore").read_text().splitlines()
    return [line.strip() for line in lines if line.strip() and line[0] != "#"]


def _ignored(relative: str, rules: list[str]) -> bool:
    parts = relative.split("/")
    prefixes = ["/".join(parts[: n + 1]) for n in range(len(parts))]
    ignored = False
    for rule in rules:
        pattern = rule.removeprefix("!").strip("/")
        names = prefixes if "/" in pattern else parts
        if any(fnmatch.fnmatchcase(name, pattern) for name in names):
            ignored = not rule.startswith("!")
    return ignored


def _in_a_clean_checkout(source: str, rules: list[str]) -> bool:
    return any(
        not _ignored(path.relative_to(REPO_ROOT).as_posix(), rules)
        for path in REPO_ROOT.glob(source)
    )


@pytest.mark.parametrize("dockerfile", _DOCKERFILES)
def test_every_copied_source_is_in_a_clean_checkout(dockerfile: str) -> None:
    rules = _ignore_rules()

    missing = [
        source
        for source in _context_sources(dockerfile)
        if not _in_a_clean_checkout(source, rules)
    ]

    assert missing == []


def test_the_sweep_reads_the_copies_from_the_context() -> None:
    sources = set(_context_sources("apps/api/Dockerfile"))

    assert {"apps/api/src/pathfinder", "ollama_models.yaml*"} <= sources
    assert sources.isdisjoint({"/uv", "/uvx"})


def test_an_ignored_path_is_not_in_a_clean_checkout() -> None:
    rules = _ignore_rules()
    paths = (
        "ollama_models.yaml",
        "ollama_models.yaml.example",
        "apps/api/.venv/bin/python",
        ".yarn/releases/yarn.cjs",
    )

    assert [_ignored(path, rules) for path in paths] == [True, False, True, False]
