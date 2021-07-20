from ipaddress import IPv4Network
from typing import Optional, Set

import boto3
from pydantic import BaseModel, constr
from structlog import get_logger


logger = get_logger(__name__)


class AWSAccount(BaseModel):
    name: str
    id: constr(regex=r"[0-9]{12}")
    # https://docs.aws.amazon.com/IAM/latest/APIReference/API_CreateRole.html#IAM-CreateRole-request-RoleName
    role_name: constr(regex=r"[\w+=,.@-]{1-64}")


class SecurityGroupRef(BaseModel):
    account: Optional[AWSAccount]
    name: Optional[str]
    group_id: constr(regex=r"sg-([0-9a-fA-F]{8}|[0-9a-f-A-F]{17})")


class SecurityGroup:
    def __init__(
        self,
        aws_sg,
        protocol: str,
        from_port: int,
        to_port: Optional[int] = None,
        description: Optional[str] = "SiteShield",
    ):
        self._aws_sg = aws_sg
        self._from_port = from_port
        self._to_port = to_port or from_port
        self._description = description
        self._protocol = protocol.lower()

    @classmethod
    def retrieve(
        cls, ec2_client, sg_ref: SecurityGroupRef, protocol: str, from_port: int, to_port: Optional[int] = None
    ):
        aws_sg = ec2_client.SecurityGroup(sg_ref.group_id)
        return cls(aws_sg, protocol=protocol, from_port=from_port, to_port=to_port)

    @property
    def authorized_ips(self) -> Set[IPv4Network]:
        """Returns the set of IPs concerned by this client

        That is the ranges of those IP Permissions whose protocol and port range match exactly.
        """
        # Don't have to check every permission:
        # a permission is a list of addresses for a given (protocol, from_port, to_port)
        # Once the tuple matches, we've found what we're looking for
        for permission in self._aws_sg.ip_permissions:
            if (
                permission.get("FromPort") == self._from_port
                and permission.get("ToPort") == self._to_port
                and permission.get("IpProtocol") == self._protocol
            ):
                return set(IPv4Network(ip_range["CidrIp"]) for ip_range in permission["IpRanges"])
        return set()

    def _ip_permission_from_cidr_set(self, cidr_set: Set[IPv4Network], with_description: bool) -> dict:
        """Creates an AWS IpPermission object for our configuration, with or without a description for each CIDR"""
        if with_description:
            base_dict = {"Description": self._description}
        else:
            base_dict = {}

        return {
            "FromPort": self._from_port,
            "ToPort": self._to_port,
            "IpProtocol": self._protocol,
            "IpRanges": [base_dict | {"CidrIp": str(cidr)} for cidr in cidr_set],
        }

    def update_from_cidr_set(self, new_set: Set[IPv4Network]):
        current_set = self.authorized_ips
        if current_set == new_set:
            logger.info("IPs didn't change")
            return

        if to_authorize := new_set - current_set:
            logger.info("Authorizing new IPs", ips=to_authorize)
            self._aws_sg.authorize_ingress(
                IpPermissions=[self._ip_permission_from_cidr_set(to_authorize, with_description=True)]
            )
        else:
            logger.info("No new IPs to authorize")

        if to_revoke := current_set - new_set:
            logger.info("Revoking old IPs", ips=to_revoke)
            self._aws_sg.revoke_ingress(
                IpPermissions=[self._ip_permission_from_cidr_set(to_revoke, with_description=False)]
            )
        else:
            logger.info("No old IPs to revoke")


def work():
    ec2 = boto3.resource("ec2")
    sg_ref = SecurityGroupRef(group_id="sg-1234567890abcdef1")
    sg = SecurityGroup.retrieve(ec2_client=ec2, from_port=1234, to_port=1234, protocol="tcp", sg_ref=sg_ref)

    new_ips = {
        IPv4Network("10.0.0.1/32"),
        IPv4Network("10.0.0.0/24"),
        IPv4Network("10.0.0.4/32"),
    }
    sg.update_from_cidr_set(new_ips)
