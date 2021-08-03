from ipaddress import IPv4Network
from typing import Optional, Set

from pydantic import BaseModel, constr, Field
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
    protocol: constr(to_lower=True)
    from_port: int
    to_port: Optional[int]
    description: Optional[str] = Field("SiteShield")


class SecurityGroupChangeResult(BaseModel):
    authorized: Set[IPv4Network]
    revoked: Set[IPv4Network]


class SecurityGroup:
    def __init__(
        self,
        aws_sg,
        sg_ref,
    ):
        self._aws_sg = aws_sg
        self._sg_ref = sg_ref

    @classmethod
    def retrieve(cls, ec2_client, sg_ref: SecurityGroupRef):
        aws_sg = ec2_client.SecurityGroup(sg_ref.group_id)
        return cls(aws_sg, sg_ref)

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
                permission.get("FromPort") == self._sg_ref.from_port
                and permission.get("ToPort") == self._sg_ref.to_port
                and permission.get("IpProtocol") == self._sg_ref.protocol
            ):
                return set(IPv4Network(ip_range["CidrIp"]) for ip_range in permission["IpRanges"])
        return set()

    def _ip_permission_from_cidr_set(self, cidr_set: Set[IPv4Network], with_description: bool) -> dict:
        """Creates an AWS IpPermission object for our configuration, with or without a description for each CIDR"""
        if with_description:
            base_dict = {"Description": self._sg_ref.description}
        else:
            base_dict = {}

        return {
            "FromPort": self._sg_ref.from_port,
            "ToPort": self._sg_ref.to_port,
            "IpProtocol": self._sg_ref.protocol,
            "IpRanges": [base_dict | {"CidrIp": str(cidr)} for cidr in cidr_set],
        }

    def update_from_cidr_set(self, new_set: Set[IPv4Network]):
        result = SecurityGroupChangeResult(authorized=set(), revoked=set())

        current_set = self.authorized_ips

        if to_authorize := new_set - current_set:
            result.authorized = to_authorize
            self._aws_sg.authorize_ingress(
                IpPermissions=[self._ip_permission_from_cidr_set(to_authorize, with_description=True)]
            )
        else:
            logger.debug("No new IPs to authorize")

        if to_revoke := current_set - new_set:
            result.revoked = to_revoke
            self._aws_sg.revoke_ingress(
                IpPermissions=[self._ip_permission_from_cidr_set(to_revoke, with_description=False)]
            )
        else:
            logger.debug("No old IPs to revoke")

        return result
