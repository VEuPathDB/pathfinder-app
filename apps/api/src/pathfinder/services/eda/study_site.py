"""The site a study opens on, and the refusal a study another site publishes gets."""

from __future__ import annotations

from collections.abc import Sequence

from veupathdb.eda import EdaPermissionEntry
from veupathdb.wdk import get_site
from veupathdb_mcp.catalog import sites_publishing
from veupathdb_mcp.embeddings import SemanticIndexUnavailableError

from pathfinder.platform.errors import AppError, ErrorCode

# The label a study card carries when no genomics site publishes its dataset.
PORTAL = "portal"
_PORTAL_NAME = "the VEuPathDB Portal"


class StudyOnAnotherSiteError(AppError):
    """The study is published on another site, so its genes are not this site's."""

    def __init__(self, sentence: str) -> None:
        super().__init__(
            code=ErrorCode.VALIDATION_ERROR,
            title="Study is on another site",
            status=422,
            detail=sentence,
        )


class StudySitesUnreadableError(AppError):
    """The store that knows which sites publish a study did not answer."""

    def __init__(self) -> None:
        super().__init__(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            title="Study sites are unavailable",
            status=503,
            detail=(
                "The sites that publish this study cannot be read now. "
                "Open it again in a moment."
            ),
        )


def _name(site_id: str) -> str:
    return _PORTAL_NAME if site_id == PORTAL else get_site(site_id).name


def _joined(names: Sequence[str], word: str) -> str:
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} {word} {names[-1]}"


def not_here(site_id: str, sites: Sequence[str], *, own: bool) -> str | None:
    """Why a study that ``sites`` publish does not open on ``site_id``, or None.

    The portal opens every study, and the researcher's own study is on its
    site.
    """
    if own or site_id in sites or get_site(site_id).is_portal:
        return None
    names = [_name(site) for site in sites]
    return (
        f"This study is on {_joined(names, 'and')}; its genes are not "
        f"{get_site(site_id).name} genes. Ask on {_joined(names, 'or')}."
    )


async def refuse_a_study_another_site_publishes(
    site_id: str, dataset_id: str, *, entry: EdaPermissionEntry
) -> None:
    """Refuse to open a study on a site that does not publish it."""
    if entry.is_user_study or get_site(site_id).is_portal:
        return
    try:
        published = await sites_publishing([dataset_id])
    except SemanticIndexUnavailableError as exc:
        raise StudySitesUnreadableError from exc
    sentence = not_here(site_id, published.get(dataset_id, [PORTAL]), own=False)
    if sentence is not None:
        raise StudyOnAnotherSiteError(sentence)
