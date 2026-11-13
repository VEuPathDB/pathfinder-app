"""The site's page of one record."""

from veupathdb.wdk import get_site

_PAGE_OF = {"transcript": "gene"}


def record_page_url(site_id: str, record_type: str, record_id: str) -> str:
    page = _PAGE_OF.get(record_type, record_type)
    return f"{get_site(site_id).web_base_url}/app/record/{page}/{record_id}"


__all__ = ["record_page_url"]
