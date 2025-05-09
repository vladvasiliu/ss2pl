from datetime import datetime
from ipaddress import IPv4Network
import requests
from typing import Set, AnyStr, List, Optional
from urllib.parse import urljoin

from akamai.edgegrid import EdgeGridAuth
from pydantic import ConfigDict, BaseModel, PositiveInt, SecretStr, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from structlog import get_logger

logger = get_logger(__name__)


class AkamaiSettings(BaseSettings):
    host: HttpUrl
    client_secret: SecretStr
    access_token: SecretStr
    client_token: SecretStr
    model_config = SettingsConfigDict(env_prefix="akamai_", case_sensitive=False)


def snake_to_lower_camel_case(string: str) -> str:
    word_list = string.split("_")
    return "".join([word_list[0], *[word.capitalize() for word in word_list[1:]]])


class AkamaiModel(BaseModel):
    model_config = ConfigDict(extra="ignore", alias_generator=snake_to_lower_camel_case)


class SiteShieldMap(AkamaiModel):
    id: PositiveInt
    acknowledged: bool
    acknowledge_required_by: Optional[datetime] = None
    acknowledged_on: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    current_cidrs: Set[IPv4Network]
    proposed_cidrs: Set[IPv4Network]
    map_alias: str
    rule_name: str
    service: str


class AkamaiClient:
    def __init__(self, settings: AkamaiSettings):
        self._base_url = settings.host
        self._session = requests.Session()
        self._session.auth = EdgeGridAuth(
            settings.client_token.get_secret_value(),
            settings.client_secret.get_secret_value(),
            settings.access_token.get_secret_value(),
        )

    def _get(self, endpoint: AnyStr) -> dict:
        url = urljoin(self._base_url.unicode_string(), endpoint)
        response = self._session.get(url)
        response.raise_for_status()
        return response.json()

    def _post(self, endpoint: AnyStr) -> dict:
        url = urljoin(self._base_url.unicode_string(), endpoint)
        response = self._session.post(url)
        response.raise_for_status()
        return response.json()

    def list_maps(self) -> List[SiteShieldMap]:
        return [SiteShieldMap(**map_dict) for map_dict in self._get("/siteshield/v1/maps")["siteShieldMaps"]]

    def get_map(self, map_id: int) -> SiteShieldMap:
        # Documentation is wrong, the SiteShield Map is the base object, not the value of a "siteShieldMap" key.
        response = self._get(f"/siteshield/v1/maps/{map_id}")
        return SiteShieldMap(**response)

    def acknowledge_map(self, map_id: int) -> SiteShieldMap:
        log = logger.bind(
            **{
                "event.action": "siteshield-map-acknowledge",
                "event.category": "configuration",
                "event.type": "change",
            }
        )
        try:
            response = self._post(f"/siteshield/v1/maps/{map_id}/acknowledge")
        except Exception as e:
            log.warning("Failed to acknowledge SiteShield Map", exc_info=e, **{"event.outcome": "failure"})
            raise e
        log.info("Acknowledged SiteShield Map", **{"event.outcome": "success"})
        return SiteShieldMap(**response)
