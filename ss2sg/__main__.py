import json
from pathlib import Path
from sys import exit
from typing import Optional, Union
from uuid import uuid4

import boto3
from pydantic import BaseSettings, conlist, PositiveInt, Field
import structlog
from structlog.contextvars import bind_contextvars, merge_contextvars, unbind_contextvars

from .akamai import AkamaiClient, AkamaiSettings, SiteShieldMap
from .aws import SecurityGroupRef, SecurityGroup, SecurityGroupChangeResult

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
    ss_map_to_sg_mapping: dict[PositiveInt, conlist(item_type=SecurityGroupRef, min_items=1)]


class AWSSettings(BaseSettings):
    secret_name: str
    secret_region: str
    profile_name: Optional[str] = Field(..., env="aws_profile")

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
        else:
            return cls(aws_settings, settings)

    def update_sg_from_ss_map(self, ss: SiteShieldMap, sg_ref: SecurityGroupRef) -> SecurityGroupChangeResult:
        if sg_ref.account:
            session = sg_ref.account.get_session(exec_id=EXECUTION_ID, aws_profile_name=self._aws_settings.profile_name)
        else:
            session = boto3.session.Session(profile_name=self._aws_settings.profile_name)
        ec2 = session.resource("ec2", region_name=sg_ref.region_name)
        sg = SecurityGroup.retrieve(ec2_client=ec2, sg_ref=sg_ref)
        return sg.update_from_cidr_set(ss.proposed_cidrs)

    def work(self):
        c = AkamaiClient(self._settings.akamai)

        maps_to_consider = c.list_maps()
        if not maps_to_consider:
            logger.warning("No SiteShield maps found")
            return
        else:
            logger.info("Retrieved SiteShield maps", maps=[m.id for m in maps_to_consider])

        maps_to_consider = [
            m for m in maps_to_consider if not m.acknowledged and m.id in self._settings.ss_map_to_sg_mapping.keys()
        ]

        if not maps_to_consider:
            logger.info("No unacknowledged maps")
            return

        for ss_map in maps_to_consider:
            context_dict = dict(
                map_id=ss_map.id, map_alias=ss_map.map_alias, proposed_ips=[str(x) for x in ss_map.proposed_cidrs]
            )
            bind_contextvars(**context_dict)
            if not ss_map.proposed_cidrs:
                logger.warning("Empty proposed CIDR list!")
            else:
                failed = False
                for sg_ref in self._settings.ss_map_to_sg_mapping[ss_map.id]:
                    bind_contextvars(sg_id=sg_ref.group_id)
                    try:
                        result = self.update_sg_from_ss_map(ss_map, sg_ref)
                    except Exception as e:
                        logger.warning("Update security group", success=False, exc_info=e)
                        failed = True
                    else:
                        logger.info(
                            "Update security group",
                            success=True,
                            authorized_ips=[str(x) for x in result.authorized],
                            revoked_ips=[str(x) for x in result.revoked],
                        )
                    finally:
                        unbind_contextvars("sg_id")

                if failed:
                    logger.warning("Failed to update security groups, won't acknowledge new SiteShield map")
                else:
                    try:
                        c.acknowledge_map(ss_map.id)
                    except Exception as e:
                        logger.warning("Acknowledge SiteShield Map", success=False, exc_info=e)
                    else:
                        logger.info("Acknowledge SiteShield Map", success=True)
            unbind_contextvars(*context_dict.keys())


if __name__ == "__main__":
    bind_contextvars(execution_id=EXECUTION_ID)
    try:
        app = App.configure_from_env(".env")
        app.work()
    except Exception as exc:
        logger.error(exc, exc_info=exc)
        exit(1)
