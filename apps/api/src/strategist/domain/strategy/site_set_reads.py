from __future__ import annotations

from collections.abc import Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field
from veupathdb_mcp.catalog import ParameterInfo

from strategist.domain.strategy.operational_spec import OperationalSpec


def site_set_names(infos: Iterable[ParameterInfo]) -> frozenset[str]:
    return frozenset(info.name for info in infos if info.site_set)


def searches_holding_values(*specs: OperationalSpec | None) -> set[str]:
    return {
        c.search_name
        for spec in specs
        if spec is not None
        for c in spec.criteria
        if c.resolved_params
    }


class SiteSetReads(BaseModel):
    model_config = ConfigDict(frozen=True)

    by_search: dict[str, frozenset[str]] = Field(default_factory=dict)

    @classmethod
    def of(cls, sheets: Mapping[str, Iterable[ParameterInfo]]) -> SiteSetReads:
        return cls(
            by_search={name: site_set_names(infos) for name, infos in sheets.items()}
        )

    def sets_the_site(self, search_name: str, param: str) -> bool:
        return param in self.by_search.get(search_name, frozenset())

    def with_reads(self, reads: Mapping[str, frozenset[str]]) -> SiteSetReads:
        return SiteSetReads(by_search={**self.by_search, **reads})
