"""What the scripted test model reads of a run before the run starts."""

from __future__ import annotations

from assistant_core.models.scripted import current_scope_id, current_user_text


def bind_scripted_scope(site_id: str, prompt: str) -> None:
    """Hold the turn's site and message where the scripted model reads them."""
    current_scope_id.set(site_id)
    current_user_text.set(prompt)
