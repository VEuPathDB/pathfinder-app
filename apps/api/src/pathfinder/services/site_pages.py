from veupathdb.wdk import SiteInfo

from pathfinder.platform.config import BASE_PATH, get_settings


def sign_in_url(site: SiteInfo) -> str:
    if get_settings().offers_dev_site_login:
        return f"{BASE_PATH}/api/v1/dev/site-login"
    return f"{site.web_base_url}/app/user/login"


def pathfinder_page_url(site: SiteInfo) -> str:
    return f"{site.web_base_url}/app/pathfinder"
