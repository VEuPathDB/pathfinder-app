"""What the site says a criterion runs on: the type of the upload it reads, or
the assay the site's dataset record names for its study or its search."""

from __future__ import annotations

from pydantic import ConfigDict, Field
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.operational_spec import Criterion


class DataMarks(CamelModel):
    """The data the criteria of a spec run on, as read from the site.

    ``uploads`` holds the type of the upload a criterion reads, by criterion id.
    ``studies`` and ``searches`` hold the assay a dataset record names, by the
    record's id and by the one search it names.
    """

    model_config = ConfigDict(frozen=True)

    uploads: dict[str, str] = Field(default_factory=dict)
    studies: dict[str, str] = Field(default_factory=dict)
    searches: dict[str, str] = Field(default_factory=dict)

    def run_on(self, criterion: Criterion) -> str | None:
        """The data the criterion runs on: its upload's type, else its study's
        assay, else its search's assay. None when the site marks none."""
        if criterion.id in self.uploads:
            return self.uploads[criterion.id]
        study = None if criterion.analysis is None else criterion.analysis.dataset_id
        if study is not None and study in self.studies:
            return self.studies[study]
        return self.searches.get(criterion.search_name)
