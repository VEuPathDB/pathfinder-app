from __future__ import annotations

import pytest

from pathfinder.platform.errors import AuditsNotOfferedError
from pathfinder.platform.identity import AUDIT_ASSISTANT_ID, PATHFINDER_ASSISTANT_ID
from pathfinder.services.audit.offered import require_audits_offered


def test_an_audit_thread_on_a_qa_site_is_refused() -> None:
    with pytest.raises(AuditsNotOfferedError, match="PlasmoDB"):
        require_audits_offered(AUDIT_ASSISTANT_ID, "plasmodb")


def test_a_strategy_thread_on_any_site_is_not_refused() -> None:
    refused: list[str] = []
    for site_id in ("plasmodb", "veupathdb", ""):
        try:
            require_audits_offered(PATHFINDER_ASSISTANT_ID, site_id)
        except AuditsNotOfferedError:
            refused.append(site_id)

    assert refused == []


def test_an_audit_thread_that_names_no_site_is_refused() -> None:
    with pytest.raises(AuditsNotOfferedError, match="This deployment"):
        require_audits_offered(AUDIT_ASSISTANT_ID, "")
