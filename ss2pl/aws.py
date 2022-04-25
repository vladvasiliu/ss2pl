from enum import Enum
from ipaddress import IPv4Network
from typing import Optional, Set

import boto3
from pydantic import BaseModel, constr, PositiveInt
from structlog import get_logger


logger = get_logger(__name__)

SESSION_DURATION = 900


class AWSException(Exception):
    pass


class PrefixListNotFoundException(AWSException):
    pass


class TooManyEntriesException(Exception):
    pass


def _to_camel(string: str) -> str:
    return "".join(word.capitalize() for word in string.split("_"))


class AWSBaseAccount(BaseModel):
    def get_session(self, region_name: str):
        return boto3.session.Session(region_name=region_name)


class AWSAccount(AWSBaseAccount):
    name: str
    id: constr(regex=r"[0-9]{12}")
    # https://docs.aws.amazon.com/IAM/latest/APIReference/API_CreateRole.html#IAM-CreateRole-request-RoleName
    role_name: str

    def get_session(self, region_name: str):
        sts_client = boto3.client("sts")
        response = sts_client.assume_role(
            RoleArn=f"arn:aws:iam::{self.id}:role/{self.role_name}",
            RoleSessionName=f"ss2pl",
            DurationSeconds=SESSION_DURATION,
        )

        credentials = response["Credentials"]

        return boto3.session.Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
            region_name=region_name,
        )


class PrefixListState(str, Enum):
    create_in_progress = "create-in-progress"
    create_complete = "create-complete"
    create_failed = "create-failed"
    modify_in_progress = "modify-in-progress"
    modify_complete = "modify-complete"
    modify_failed = "modify-failed"
    restore_in_progress = "restore-in-progress"
    restore_complete = "restore-complete"
    restore_failed = "restore-failed"
    delete_in_progress = "delete-in-progress"
    delete_complete = "delete-complete"
    delete_failed = "delete-failed"


class PrefixListAddressFamily(str, Enum):
    ipv4 = "IPv4"
    ipv6 = "IPv6"


class PrefixListDescription(BaseModel):
    prefix_list_id: constr(regex=r"pl-([0-9a-fA-F]{8}|[0-9a-f-A-F]{17})")
    address_family: PrefixListAddressFamily
    state: PrefixListState
    state_message: Optional[str]
    prefix_list_name: str
    max_entries: PositiveInt
    version: PositiveInt

    class Config:
        alias_generator = _to_camel


class PrefixList(BaseModel):
    account: AWSAccount = AWSBaseAccount()
    name: Optional[str]
    prefix_list_id: constr(regex=r"pl-([0-9a-fA-F]{8}|[0-9a-f-A-F]{17})")
    description: Optional[str] = "SiteShield"
    region_name: str
    address_family: PrefixListAddressFamily = PrefixListAddressFamily.ipv4
    _client = None

    def _get_client(self):
        return self.account.get_session(region_name=self.region_name).client("ec2")

    def describe(self) -> PrefixListDescription:
        client = self._get_client()
        pl_list = client.describe_managed_prefix_lists(PrefixListIds=[self.prefix_list_id])["PrefixLists"]

        if not pl_list:
            raise PrefixListNotFoundException(f"Prefix list {self.prefix_list_id} not found")
        if len(pl_list) > 1:
            raise AWSException("Too many prefix lists returned")
        return PrefixListDescription(**pl_list[0])

    def get_entries(self, pl_desc: PrefixListDescription) -> Set[IPv4Network]:
        client = self._get_client()
        paginator = client.get_paginator("get_managed_prefix_list_entries")
        result = set()
        for page in paginator.paginate(
            PrefixListId=pl_desc.prefix_list_id, TargetVersion=pl_desc.version, MaxResults=pl_desc.max_entries
        ):
            result = result.union(IPv4Network(e["Cidr"]) for e in page["Entries"])
        return result

    def set_cidrs(self, cidr_set: set[IPv4Network]):
        client = self._get_client()
        desc = self.describe()
        old_entries = self.get_entries(desc)
        to_add = cidr_set - old_entries
        to_remove = old_entries - cidr_set

        new_total_count = len(old_entries) - len(to_remove) + len(to_add)

        log = logger.bind(
            **{"event.action": "prefix-list-update", "event.category": "configuration", "event.type": "change"}
        )

        if new_total_count > desc.max_entries:
            log.warning(
                "Failed to update prefix list",
                **{
                    "event.action": "prefix-list-update",
                    "event.outcome": "failure",
                    "event.reason": "Too many entries to add ({new_total_count} > {desc.max_entries})",
                },
            )
            raise TooManyEntriesException(f"Too many entries to add ({new_total_count} > {desc.max_entries})")

        if any((to_add, to_remove)):
            try:
                response = client.modify_managed_prefix_list(
                    PrefixListId=self.prefix_list_id,
                    CurrentVersion=desc.version,
                    AddEntries=[{"Cidr": str(cidr), "Description": self.description} for cidr in to_add],
                    RemoveEntries=[{"Cidr": str(cidr)} for cidr in to_remove],
                )
            except Exception as e:
                log.warning("Failed to update prefix list", exc_info=e, **{"event.outcome": "failure"})
                raise e
            result = PrefixListDescription(**response["PrefixList"])
            log.info(
                "Updated prefix list",
                **{
                    "event.outcome": "success",
                    "ss2pl.prefix_list.added": len(to_add),
                    "ss2pl.prefix_list.removed": len(to_remove),
                    "ss2pl.prefix_list.version": result.version,
                },
            )
        else:
            log.info("Nothing to do")
