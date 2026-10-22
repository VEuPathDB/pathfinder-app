from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UnservedSearch:
    where: str
    said: str
    refusals: int = 0

    def sentence(self, search_name: str, site_id: str) -> str:
        return (
            f"The search {search_name} is not served by {site_id} under "
            f"{self.where} ({self.said})."
        )


class SearchNotServedError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
