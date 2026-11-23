from typing import Final

from strategist.ai.audit.mock import (
    build_audit_mock,
    build_review_mock,
    build_synthesis_mock,
)
from strategist.ai.models.mock import get_mock_model
from strategist.ai.models.mock.reading import scripted_intent, scripted_operators
from strategist.ai.models.mock.route import scripted_route
from strategist.ai.scripted import ScriptedDeployment
from strategist_scripted.decisions import no_decision
from strategist_scripted.judge import injection_judge

SCRIPTED: Final = ScriptedDeployment(
    model=get_mock_model,
    intent=scripted_intent,
    route=scripted_route,
    operators=scripted_operators,
    decisions=no_decision,
    injection_judge=injection_judge,
    auditor=build_audit_mock,
    reviewer=build_review_mock,
    synthesis=build_synthesis_mock,
)
