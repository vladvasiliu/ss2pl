from datetime import datetime
import os
from io import StringIO
from pathlib import Path
import sys
import traceback
from typing import Union, Dict, Any
from uuid import uuid4

import ecs_logging
import structlog
from structlog.contextvars import bind_contextvars, merge_contextvars, unbind_contextvars

from .akamai import AkamaiClient
from .settings import Settings, AppSettings


def _format_error(event_dict):
    if exc_info := event_dict.pop("exc_info", None):
        # Shamelessly lifted from stdlib's logging module
        sio = StringIO()

        traceback.print_exception(exc_info.__class__, exc_info, exc_info.__traceback__, None, sio)
        s = sio.getvalue()
        sio.close()
        if s[-1:] == "\n":
            s = s[:-1]

        event_dict["error"] = {
            "stack_trace": s,
            "message": str(exc_info),
            "type": exc_info.__class__.__qualname__,
        }
    return event_dict


class ECSFormatter(ecs_logging.StructlogFormatter):
    def format_to_ecs(self, event_dict):  # type: (Dict[str, Any]) -> Dict[str, Any]
        event_dict = super(ECSFormatter, self).format_to_ecs(event_dict)
        event_dict = _format_error(event_dict)
        return event_dict


structlog.configure(
    cache_logger_on_first_use=True,
    processors=[
        merge_contextvars,
        structlog.threadlocal.merge_threadlocal_context,
        # structlog.processors.add_log_level,
        # structlog.processors.StackInfoRenderer(),
        # structlog.processors.format_exc_info,
        ECSFormatter(),
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)


EXECUTION_ID = str(uuid4())
bind_contextvars(execution_id=EXECUTION_ID)


class AppException(Exception):
    pass


def _get_root_cause(exc: Exception) -> str:
    cause = exc
    result = ""
    while cause := cause.__cause__:
        result = str(cause)
    return result


class App:
    def __init__(self, aws_settings: AppSettings, settings: Settings):
        self._aws_settings = aws_settings
        self._settings = settings

    @classmethod
    def configure_from_env(cls, env_file: Union[None, Path, str]):
        logger = structlog.get_logger(**{"event.action": "load-config", "event.category": "configuration"})
        try:
            app_settings = AppSettings(_env_file=env_file)
            settings = app_settings.fetch_settings()
            if app_settings.aws_profile:
                os.environ["AWS_PROFILE"] = app_settings.aws_profile
        except Exception as e:
            logger.exception(
                "Failed to load settings",
                exc_info=e,
                **{"event.outcome": "failure", "event.reason": _get_root_cause(e)},
            )
            raise AppException("Failed to load settings") from e
        else:
            bind_contextvars()
            logger.info("Loaded settings", **{"event.outcome": "success"})
        return cls(app_settings, settings)

    def work(self):
        c = AkamaiClient(self._settings.akamai)
        logger = structlog.get_logger()

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
                action="Update PrefixList",
            )
            bind_contextvars(**context_dict)
            try:
                if not ss_map.proposed_cidrs:
                    logger.warning("Empty proposed CIDR list!")
                else:
                    pl_ref.set_cidrs(ss_map.proposed_cidrs)
                    bind_contextvars(action="Acknowledge SiteShield")
                    c.acknowledge_map(ss_map.id)
            except Exception as e:
                logger.exception(str(e), exc_info=e)
            finally:
                unbind_contextvars(*context_dict.keys())


if __name__ == "__main__":
    start_time = datetime.now()

    try:
        app = App.configure_from_env(".env")
        app.work()
    except Exception as exc:
        # logger.exception(str(exc), exc_info=exc)
        exit_code = 1
    else:
        exit_code = 0
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    structlog.get_logger().info("Shutting down", run_time=duration, process=dict(exit_code=exit_code))
    sys.exit(exit_code)
