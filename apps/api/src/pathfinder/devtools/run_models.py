"""One model for every role of a debugger or eval run, and each role's model as the code resolves it."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from pathfinder.ai.agents._model_resolution import resolve_orchestrator_model_entry
from pathfinder.ai.capabilities import security
from pathfinder.ai.conversation import title_generator
from pathfinder.assistants.registry import assistant_role_models
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.platform.model_catalog import deployment_may_pay, get_model_entry
from pathfinder.platform.pinned_model import pin_model, pinned_model
from pathfinder.platform.tiers import KNOWN_ROLES


class RunModelError(RuntimeError):
    pass


@contextmanager
def pin_every_role(model_id: str) -> Iterator[None]:
    if get_model_entry(model_id) is None:
        msg = f"{model_id} is not in the model catalog"
        raise RunModelError(msg)
    if not deployment_may_pay(model_id):
        msg = f"the deployment does not pay for {model_id}, and a run uses its key"
        raise RunModelError(msg)
    with pin_model(model_id):
        yield


def pinned_phase_models() -> dict[str, str]:
    pinned = pinned_model()
    return {} if pinned is None else dict.fromkeys(KNOWN_ROLES, pinned)


def resolved_roles() -> dict[str, str]:
    judge = (
        {"injection_judge": security.judge_model_id()}
        if get_settings().input_screening_enabled
        else {}
    )
    return {
        **assistant_role_models(PATHFINDER_ASSISTANT_ID, pinned_phase_models()),
        "title_generator": title_generator.title_model_id() or "",
        "note_compactor": resolve_orchestrator_model_entry(None, None).id,
        **judge,
    }


def role_lines(roles: Mapping[str, str]) -> list[str]:
    return [f"{role}: {roles[role]}" for role in sorted(roles)]


def roles_off(model_id: str, roles: Mapping[str, str]) -> str:
    off = [
        f"{role} ({roles[role]})" for role in sorted(roles) if roles[role] != model_id
    ]
    return f"roles not on {model_id}: {', '.join(off)}" if off else ""


@contextmanager
def pinned_run(model_id: str | None, *, via_worker: bool) -> Iterator[dict[str, str]]:
    if model_id is None:
        yield {}
        return
    if via_worker:
        msg = (
            "a model for every role does not combine with --via-worker: the worker "
            "runs the title generator, the note compactor and the injection judge "
            "on its own models"
        )
        raise RunModelError(msg)
    with pin_every_role(model_id):
        roles = resolved_roles()
        off = roles_off(model_id, roles)
        if off:
            raise RunModelError(off)
        yield roles


__all__ = [
    "RunModelError",
    "pin_every_role",
    "pinned_phase_models",
    "pinned_run",
    "resolved_roles",
    "role_lines",
    "roles_off",
]
