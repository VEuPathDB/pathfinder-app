"""What the site says a criterion runs on: the type of the upload it reads, or
the assay the site's dataset record names for its study or its search."""

from __future__ import annotations

from pydantic import ConfigDict, Field
from veupathdb.model import CamelModel

from strategist.domain.strategy.operational_spec import Criterion
from strategist.domain.unread import Unread

_NOT_READ = Unread(reason="the site's marks were not read for this search")


class DataMarks(CamelModel):
    """The data the criteria of a spec run on, as read from the site.

    ``uploads`` holds the type of the upload a criterion reads, by criterion id.
    ``studies`` and ``searches`` hold the assay a dataset record names, by the
    record's id and by the one search it names, or why the read failed.
    ``read_for`` holds the search names the marks were read for.
    """

    model_config = ConfigDict(frozen=True)

    uploads: dict[str, str] = Field(default_factory=dict)
    studies: dict[str, str | Unread] = Field(default_factory=dict)
    searches: dict[str, str | Unread] = Field(default_factory=dict)
    read_for: frozenset[str] = frozenset()

    def run_on(self, criterion: Criterion) -> str | Unread | None:
        """The data the criterion runs on: its upload's type, else its study's
        assay, else its search's assay. None when the site marks none, and
        Unread when its search was not read or its read failed."""
        if criterion.id in self.uploads:
            return self.uploads[criterion.id]
        study = None if criterion.analysis is None else criterion.analysis.dataset_id
        if study is not None and study in self.studies:
            return self.studies[study]
        if criterion.search_name not in self.read_for:
            return _NOT_READ
        return self.searches.get(criterion.search_name)
