from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module

from fastapi import APIRouter
from pydantic_ai.models import Model
from veupathdb_mcp.catalog import DecisionsTransport

from strategist.ai.graph.state import PipelineState
from strategist.ai.lead.intent import UserIntent
from strategist.platform.config import SCRIPTED_PACKAGE


@dataclass(frozen=True)
class ScriptedDeployment:
    model: Callable[[], Model]
    intent: Callable[[PipelineState, str], UserIntent]
    route: Callable[[str], DecisionsTransport]
    operators: Callable[[PipelineState], DecisionsTransport]
    decisions: DecisionsTransport
    injection_judge: Callable[[], Model]
    auditor: Callable[[], Model]
    reviewer: Callable[[], Model]
    synthesis: Callable[[], Model]
    dev_router: APIRouter


def scripted() -> ScriptedDeployment:
    deployment: ScriptedDeployment = import_module(SCRIPTED_PACKAGE).SCRIPTED
    return deployment


__all__ = ["ScriptedDeployment", "scripted"]
