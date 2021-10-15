from datetime import datetime
import json
import os
from pathlib import Path
from sys import exit
from typing import Optional, Union
from uuid import uuid4

import boto3
from pydantic import BaseSettings, PositiveInt, Field
import structlog
from structlog.contextvars import bind_contextvars, merge_contextvars, unbind_contextvars

from .akamai import AkamaiClient, AkamaiSettings
from .aws import PrefixList

structlog.configure(
    cache_logger_on_first_use=True,
    processors=[
        merge_contextvars,
        structlog.threadlocal.merge_threadlocal_context,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)

EXECUTION_ID = str(uuid4())

logger = structlog.get_logger(__name__)


class Settings(BaseSettings):
    akamai: AkamaiSettings
    ss_to_pl: dict[PositiveInt, PrefixList]


class AWSSettings(BaseSettings):
    secret_name: str
    secret_region: str
    profile_name: Optional[str] = Field(None, env="aws_profile")

    class Config:
        env_prefix = "aws_"
        case_sensitive = False

    def fetch_settings(self) -> Settings:
        """Gets a secret from AWS Secrets Manager. Expects JSON input.
        It attempts to use the instance or task credentials.
        :return: Settings based on the secret
        """
        session = boto3.session.Session(region_name=self.secret_region, profile_name=self.profile_name)
        client = session.client(
            service_name="secretsmanager",
            region_name=self.secret_region,
        )

        try:
            secret_value = client.get_secret_value(SecretId=self.secret_name)
        except Exception as e:
            raise Exception("Failed to retrieve secret value.") from e

        if "SecretString" in secret_value:
            secret = secret_value["SecretString"]
        else:
            raise Exception("The specified secret is malformed.")

        return Settings(**json.loads(secret))


class App:
    def __init__(self, aws_settings: AWSSettings, settings: Settings):
        self._aws_settings = aws_settings
        self._settings = settings

    @classmethod
    def configure_from_env(cls, env_file: Union[None, Path, str]):
        try:
            aws_settings = AWSSettings(_env_file=env_file)
            settings = aws_settings.fetch_settings()
        except Exception as e:
            raise Exception("Failed to load settings") from e

        if aws_settings.profile_name:
            os.environ["AWS_PROFILE"] = aws_settings.profile_name
        return cls(aws_settings, settings)

    def work(self):
        c = AkamaiClient(self._settings.akamai)

        maps_to_consider = c.list_maps()
        if not maps_to_consider:
            logger.warning("No SiteShield maps found")
            return
        else:
            logger.info("Retrieved SiteShield maps", maps=[m.id for m in maps_to_consider])

        maps_to_consider = [
            m for m in maps_to_consider if not m.acknowledged and m.id in self._settings.ss_to_pl.keys()
        ]

        if not maps_to_consider:
            logger.info("No unacknowledged maps")
            return

        for ss_map in maps_to_consider:
            pl_ref = self._settings.ss_to_pl[ss_map.id]
            context_dict = dict(
                map_id=ss_map.id,
                map_alias=ss_map.map_alias,
                proposed_ips=[str(x) for x in ss_map.proposed_cidrs],
                pl_id=pl_ref.prefix_list_id,
                pl_name=pl_ref.name,
            )
            bind_contextvars(**context_dict)
            if not ss_map.proposed_cidrs:
                logger.warning("Empty proposed CIDR list!")
            else:
                pl_ref.set_cidrs(ss_map.proposed_cidrs)
                c.acknowledge_map(ss_map.id)
            unbind_contextvars(*context_dict.keys())


if __name__ == "__main__":
    bind_contextvars(execution_id=EXECUTION_ID)
    start_time = datetime.now()
    try:
        app = App.configure_from_env(".env")
        app.work()
    except Exception as exc:
        logger.error(str(exc), exc_info=exc)
        exit_code = 1
    else:
        exit_code = 0
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    logger.info("Shutting down", run_time=duration)
    exit(exit_code)
