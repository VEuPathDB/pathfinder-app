from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from strategist.platform.paths import REPO_ROOT

_SCRIPTED = "strategist_scripted"


class _Stage(BaseModel):
    model_config = ConfigDict(frozen=True)

    from_line: str
    name: str
    lines: tuple[str, ...]


def _stages() -> list[_Stage]:
    text = (REPO_ROOT / "apps/api/Dockerfile").read_text().replace("\\\n", " ")
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


def _copied_sources(stage_name: str) -> set[str]:
    (stage,) = [stage for stage in _stages() if stage.name == stage_name]
    sources: set[str] = set()
    for line in stage.lines:
        words = line.split()
        if words[:1] != ["COPY"] or any(w.startswith("--from=") for w in words):
            continue
        paths = [word for word in words[1:] if not word.startswith("--")]
        sources.update(paths[:-1])
    return sources


def _yaml(relative: str) -> Any:
    return yaml.safe_load((REPO_ROOT / relative).read_text().replace(" !override", ""))


def test_the_last_stage_is_the_runtime_stage() -> None:
    assert _stages()[-1].from_line == "FROM runtime"


def test_only_the_e2e_stage_copies_the_scripted_package() -> None:
    copying = [s.name for s in _stages() if any(_SCRIPTED in line for line in s.lines)]

    assert copying == ["e2e"]


def test_the_runtime_stage_copies_the_application_package_only() -> None:
    sources = _copied_sources("runtime")

    assert "apps/api/src/strategist" in sources
    assert {source.rstrip("/") for source in sources} & {"apps/api/src"} == set()


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
