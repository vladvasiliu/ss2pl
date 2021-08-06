from uuid import uuid4

import boto3
from pydantic import BaseSettings, conlist, PositiveInt
import structlog
from structlog.contextvars import bind_contextvars, merge_contextvars, unbind_contextvars

from .akamai import AkamaiClient, AkamaiSettings, SiteShieldMap
from .aws import SecurityGroupRef, SecurityGroup


structlog.configure(
    cache_logger_on_first_use=True,
    processors=[
        merge_contextvars,
        structlog.threadlocal.merge_threadlocal_context,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.dev.ConsoleRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger(__name__)


class Settings(BaseSettings):
    akamai_settings: AkamaiSettings = AkamaiSettings(_env_file=".env")
    ss_map_to_sg_mapping: dict[PositiveInt, conlist(item_type=SecurityGroupRef, min_items=1)]


def update_sg_from_ss_map(ss: SiteShieldMap, sg_ref: SecurityGroupRef):
    ec2 = boto3.resource("ec2")
    sg = SecurityGroup.retrieve(ec2_client=ec2, sg_ref=sg_ref)
    sg.update_from_cidr_set(ss.proposed_cidrs)


def work(settings: Settings):
    c = AkamaiClient(settings.akamai_settings)

    maps_to_consider = c.list_maps()
    logger.info("Retrieved SiteShield maps", maps=[m.id for m in maps_to_consider])

    maps_to_consider = [
        m for m in maps_to_consider if not m.acknowledged and m.id in settings.ss_map_to_sg_mapping.keys()
    ]

    if not maps_to_consider:
        logger.info("No unacknowledged maps")
        return

    for ss_map in maps_to_consider:
        bind_contextvars(map_id=ss_map.id, proposed_ips=ss_map.proposed_cidrs)
        failed = False
        for sg_ref in settings.ss_map_to_sg_mapping[ss_map.id]:
            bind_contextvars(sg_id=sg_ref.group_id)
            try:
                update_sg_from_ss_map(ss_map, sg_ref)
            except Exception as e:
                logger.warning("Update security group", success=False, exc_info=e)
                failed = True
            else:
                logger.info("Update security group", success=True)
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
        unbind_contextvars("map_id", "proposed_ips")


if __name__ == "__main__":
    bind_contextvars(execution_id=str(uuid4()))

    s = Settings(
        ss_map_to_sg_mapping={
            1234567: [SecurityGroupRef(group_id="sg-1234567890abcdef1", from_port=1234, to_port=1234, protocol="tcp")]
        },
    )

    work(s)
