from ipaddress import IPv4Network
from typing import Optional, List

from pydantic import BaseModel, constr


def snake_to_camelcase(string: str) -> str:
    return "".join([word.capitalize() for word in string.split("_")])


class IPRange(BaseModel):
    cidr_ip: IPv4Network
    description: constr(max_length=255)

    class Config:
        alias_generator = snake_to_camelcase


class IPPermission(BaseModel):
    from_port: int
    to_port: int
    ip_protocol: str
    ip_ranges: List[IPRange]
    to_port: int

    class Config:
        alias_generator = snake_to_camelcase


class AWSAccount(BaseModel):
    name: str
    id: constr(regex=r"[0-9]{12}")
    # https://docs.aws.amazon.com/IAM/latest/APIReference/API_CreateRole.html#IAM-CreateRole-request-RoleName
    role_name: constr(regex=r"[\w+=,.@-]{1-64}")


class SecurityGroupConf(BaseModel):
    name: str
    id: constr(regex=r"sg-([0-9a-fA-F]{8}|[0-9a-f-A-F]{17})")
    account: Optional[AWSAccount]


class SecurityGroup(SecurityGroupConf):
    ip_permissions: List[IPPermission]
