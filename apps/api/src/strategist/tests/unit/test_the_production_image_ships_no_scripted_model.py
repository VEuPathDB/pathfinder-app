from pathlib import PurePosixPath
from typing import Any

import pytest
import yaml
from pydantic import BaseModel, ConfigDict

from strategist.platform.paths import REPO_ROOT

_SCRIPTED = "strategist_scripted"
_SCRIPTED_SOURCE = PurePosixPath("apps/api/src/strategist_scripted")


class _Stage(BaseModel):
    model_config = ConfigDict(frozen=True)

    from_line: str
    name: str
    lines: tuple[str, ...]


def _stages(dockerfile: str | None = None) -> list[_Stage]:
    raw = dockerfile or (REPO_ROOT / "apps/api/Dockerfile").read_text()
    text = raw.replace("\\\n", " ")
    stages: list[_Stage] = []
    for line in text.splitlines():
        words = line.split()
        if words[:1] == ["FROM"]:
            name = words[3] if words[2:3] == ["AS"] else ""
            stages.append(_Stage(from_line=line.strip(), name=name, lines=()))
        elif stages:
            last = stages[-1]
            stages[-1] = last.model_copy(update={"lines": (*last.lines, line)})
    return stages


def _copied_sources(stage_name: str, dockerfile: str | None = None) -> set[str]:
    (stage,) = [stage for stage in _stages(dockerfile) if stage.name == stage_name]
    sources: set[str] = set()
    for line in stage.lines:
        words = line.split()
        if words[:1] != ["COPY"] or any(w.startswith("--from=") for w in words):
            continue
        paths = [word for word in words[1:] if not word.startswith("--")]
        sources.update(paths[:-1])
    return sources


def _ships_scripted(source: str) -> bool:
    copied = PurePosixPath(source.rstrip("*"))
    return copied == _SCRIPTED_SOURCE or copied in _SCRIPTED_SOURCE.parents


def _runtime_ships_scripted(dockerfile: str | None = None) -> bool:
    return any(_ships_scripted(src) for src in _copied_sources("runtime", dockerfile))


def _yaml(relative: str) -> Any:
    return yaml.safe_load((REPO_ROOT / relative).read_text().replace(" !override", ""))


def test_the_last_stage_is_the_runtime_stage() -> None:
    assert _stages()[-1].from_line == "FROM runtime"


def test_only_the_e2e_stage_copies_the_scripted_package() -> None:
    copying = [s.name for s in _stages() if any(_SCRIPTED in line for line in s.lines)]

    assert copying == ["e2e"]


def test_the_runtime_stage_copies_no_ancestor_of_the_scripted_package() -> None:
    assert "apps/api/src/strategist" in _copied_sources("runtime")
    assert _runtime_ships_scripted() is False


def test_the_final_stage_copies_nothing() -> None:
    assert [line for line in _stages()[-1].lines if line.split()[:1] == ["COPY"]] == []


@pytest.mark.parametrize("broad", ["COPY . .", "COPY apps/api apps/api"])
def test_a_broad_runtime_copy_is_caught(broad: str) -> None:
    dockerfile = f"FROM python:3.14-slim AS runtime\n{broad}\nFROM runtime\n"

    assert _runtime_ships_scripted(dockerfile) is True


def test_the_e2e_compose_builds_the_e2e_stage() -> None:
    services = _yaml("docker-compose.e2e.yml")["services"]

    assert [services[name]["build"]["target"] for name in ("api", "worker")] == [
        "e2e",
        "e2e",
    ]


def test_ci_builds_the_e2e_stage_for_the_e2e_images() -> None:
    steps = _yaml(".github/workflows/ci.yml")["jobs"]["e2e-build"]["steps"]
    (step,) = [step for step in steps if step.get("name") == "Build the api image"]

    assert (step["with"]["file"], step["with"]["target"]) == (
        "apps/api/Dockerfile",
        "e2e",
    )
