"""Routes requests to a VEuPathDB portal or component site and owns their clients."""

import threading
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import yaml
from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from pathfinder.integrations.veupathdb.client import VEuPathDBClient
from pathfinder.integrations.veupathdb.site_search_client import SiteSearchClient
from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import ErrorCode, NotFoundError

logger = get_logger(__name__)


class SiteConfig(BaseModel):
    """Validated configuration for a single VEuPathDB site."""

    name: str = ""
    display_name: str = ""
    base_url: str = ""
    project_id: str = ""
    is_portal: bool = False


class RoutingConfig(BaseModel):
    """Validated routing/timeout configuration."""

    portal_timeout: float = 120.0
    component_timeout: float = 30.0


class SitesConfig(BaseModel):
    """Top-level sites configuration parsed from YAML."""

    sites: dict[str, SiteConfig] = Field(default_factory=dict)
    default_site: str = "veupathdb"
    routing: RoutingConfig = Field(default_factory=RoutingConfig)


@lru_cache
def load_sites_config(config_path: str | None = None) -> SitesConfig:
    """Loads and validates the sites configuration from YAML. An empty path selects
    the bundled sites.yaml next to this module."""
    path = (
        Path(config_path).resolve()
        if (config_path and config_path.strip())
        else Path(__file__).parent / "sites.yaml"
    )
    logger.info("Loading sites config", path=str(path))
    with path.open() as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        logger.warning("Sites config is not a dict, using defaults")
        return SitesConfig()
    config = SitesConfig.model_validate(raw)
    logger.info("Sites config loaded", num_sites=len(config.sites))
    return config


class SiteInfo(CamelModel):
    """VEuPathDB site information."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(validation_alias=AliasChoices("id", "site_id"))
    name: str
    display_name: str
    base_url: str
    project_id: str
    is_portal: bool

    @field_validator("base_url", mode="before")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/") if isinstance(v, str) else v

    @classmethod
    def from_config(cls, site_id: str, cfg: SiteConfig) -> SiteInfo:
        """Builds a SiteInfo from a validated SiteConfig."""
        return cls(
            id=site_id,
            name=cfg.name,
            display_name=cfg.display_name,
            base_url=cfg.base_url,
            project_id=cfg.project_id,
            is_portal=cfg.is_portal,
        )

    @property
    def service_url(self) -> str:
        """Returns the WDK service URL, which the configured base URL already holds."""
        return self.base_url

    @property
    def web_base_url(self) -> str:
        """Returns the web UI base URL without the service suffix."""
        return self.base_url.removesuffix("/service")

    @property
    def site_origin(self) -> str:
        """Returns the site origin, which is the scheme and host with no path.
        Site search lives at the origin, not under the WDK service prefix.
        """
        parsed = urlparse(self.base_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    @property
    def eda_base_url(self) -> str:
        """Returns the EDA service URL, which lives at the site origin."""
        return f"{self.site_origin}/eda"

    def strategy_url(self, strategy_id: int, root_step_id: int | None = None) -> str:
        """Builds a strategy URL for the web UI."""
        if root_step_id is not None:
            return f"{self.web_base_url}/app/workspace/strategies/{strategy_id}/{root_step_id}"
        return f"{self.web_base_url}/app/workspace/strategies/{strategy_id}"


class SiteRouter:
    """Selects a VEuPathDB site and owns the client for each one."""

    def __init__(self) -> None:
        settings = get_settings()
        self._config = load_sites_config(settings.veupathdb_sites_config)
        self._sites: dict[str, SiteInfo] = {}
        self._clients: dict[str, VEuPathDBClient] = {}
        self._site_search_clients: dict[str, SiteSearchClient] = {}
        self._client_lock = threading.Lock()
        self._load_sites()

    def _load_sites(self) -> None:
        """Loads the site configurations from the validated config."""
        logger.info("Loading sites", count=len(self._config.sites))
        for site_id, site_cfg in self._config.sites.items():
            self._sites[site_id] = SiteInfo.from_config(site_id, site_cfg)
        logger.info("Sites loaded", site_ids=list(self._sites.keys()))

    def get_site(self, site_id: str) -> SiteInfo:
        """Returns the site with this identifier."""
        logger.debug(
            "Getting site", site_id=site_id, available=list(self._sites.keys())
        )
        if site_id not in self._sites:
            raise NotFoundError(
                code=ErrorCode.SITE_NOT_FOUND,
                title="Site not found",
                detail=f"Unknown site: {site_id}. Available: {list(self._sites.keys())}",
            )
        return self._sites[site_id]

    def list_sites(self) -> list[SiteInfo]:
        """Returns every available site."""
        return list(self._sites.values())

    def get_client(self, site_id: str) -> VEuPathDBClient:
        """Returns the HTTP client for a site and creates it on first use."""
        if site_id in self._clients:
            return self._clients[site_id]
        with self._client_lock:
            if site_id not in self._clients:
                site = self.get_site(site_id)
                routing = self._config.routing
                settings = get_settings()
                timeout = (
                    routing.portal_timeout
                    if site.is_portal
                    else routing.component_timeout
                )
                self._clients[site_id] = VEuPathDBClient(
                    base_url=site.service_url,
                    timeout=float(timeout),
                    auth_token=settings.veupathdb_auth_token,
                )
            return self._clients[site_id]

    def get_site_search_client(self, site_id: str) -> SiteSearchClient:
        """Returns the site search client for a site and creates it on first use.
        Site search is a separate service that lives at the site origin URL.
        """
        if site_id in self._site_search_clients:
            return self._site_search_clients[site_id]
        with self._client_lock:
            if site_id not in self._site_search_clients:
                site = self.get_site(site_id)
                self._site_search_clients[site_id] = SiteSearchClient(
                    base_url=site.site_origin,
                    project_id=site.project_id,
                    timeout=float(self._config.routing.component_timeout),
                )
            return self._site_search_clients[site_id]

    async def close_all(self) -> None:
        """Closes every HTTP client."""
        for wdk_client in self._clients.values():
            await wdk_client.close()
        self._clients.clear()
        for ss_client in self._site_search_clients.values():
            await ss_client.close()
        self._site_search_clients.clear()


_router_holder: dict[str, SiteRouter] = {}
_router_lock = threading.Lock()


def get_site_router() -> SiteRouter:
    """Returns the process-wide site router."""
    if "v" in _router_holder:
        return _router_holder["v"]
    with _router_lock:
        if "v" not in _router_holder:
            _router_holder["v"] = SiteRouter()
        return _router_holder["v"]
