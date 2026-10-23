from __future__ import annotations

from pathfinder.ai.audit.auditor import AUDITOR_MODEL, audit_compile_time_models
from pathfinder.assistants.registry import (
    get_assistant_registry,
    installed_assistants,
    installed_phase_defaults,
)
from pathfinder.platform.identity import AUDIT_ASSISTANT_ID, PATHFINDER_ASSISTANT_ID
from pathfinder.platform.tiers import AUDITOR_ROLE, REVIEW_ROLE


def test_the_registry_holds_pathfinder_and_the_audit_assistant() -> None:
    registry = get_assistant_registry()

    assert set(installed_assistants()) == {PATHFINDER_ASSISTANT_ID, AUDIT_ASSISTANT_ID}
    assert set(registry.ids()) == {PATHFINDER_ASSISTANT_ID, AUDIT_ASSISTANT_ID}
    assert registry.resolve(AUDIT_ASSISTANT_ID).assistant_id == AUDIT_ASSISTANT_ID


def test_the_installed_defaults_name_both_audit_roles() -> None:
    defaults = installed_phase_defaults("openai", "balanced")

    assert {AUDITOR_ROLE, REVIEW_ROLE} <= set(defaults)


def test_the_audit_roles_read_the_user_message_as_the_auditor() -> None:
    installed = installed_assistants()[AUDIT_ASSISTANT_ID]

    assert installed.prompt_role == AUDITOR_ROLE
    assert audit_compile_time_models() == {
        AUDITOR_ROLE: AUDITOR_MODEL,
        REVIEW_ROLE: AUDITOR_MODEL,
    }
