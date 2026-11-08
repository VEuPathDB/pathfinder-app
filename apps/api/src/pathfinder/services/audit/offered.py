"""The refusal of an audit thread on a site that offers no audit."""

from __future__ import annotations

from veupathdb.wdk import get_site

from pathfinder.domain.audit.offered import offers_audits
from pathfinder.platform.errors import AuditsNotOfferedError
from pathfinder.platform.identity import AUDIT_ASSISTANT_ID


def require_audits_offered(assistant_id: str, site_id: str) -> None:
    if assistant_id != AUDIT_ASSISTANT_ID:
        return
    if not site_id:
        raise AuditsNotOfferedError(site="This deployment")
    site = get_site(site_id)
    if not offers_audits(site.base_url):
        raise AuditsNotOfferedError(site=site.name)
