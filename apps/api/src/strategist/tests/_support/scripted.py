from collections.abc import Callable
from dataclasses import replace
from typing import Any

from strategist.ai.scripted import ScriptedDeployment
from strategist_scripted import SCRIPTED


def scripted_with(**changes: Any) -> Callable[[], ScriptedDeployment]:
    changed = replace(SCRIPTED, **changes)
    return lambda: changed
