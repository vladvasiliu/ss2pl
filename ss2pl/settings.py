import json
from typing import Optional, Dict

import boto3
from pydantic import PositiveInt

from ss2pl.akamai import AkamaiSettings
from ss2pl.aws import PrefixList
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettingsException(Exception):
    pass


class Settings(BaseSettings):
    akamai: AkamaiSettings
    ss_to_pl: Dict[PositiveInt, PrefixList]


class AppSettings(BaseSettings):
    aws_secret_name: str
    aws_secret_region: str
    aws_profile: Optional[str]
    model_config = SettingsConfigDict(case_sensitive=False)

    def fetch_settings(self) -> Settings:
        """Gets a secret from AWS Secrets Manager. Expects JSON input.
        It attempts to use the instance or task credentials.
        :return: Settings based on the secret
        """
        session = boto3.session.Session(region_name=self.aws_secret_region, profile_name=self.aws_profile)
        client = session.client(
            service_name="secretsmanager",
            region_name=self.aws_secret_region,
        )

        try:
            secret_value = client.get_secret_value(SecretId=self.aws_secret_name)
        except Exception as e:
            raise AppSettingsException("Failed to retrieve secret value.") from e

        if "SecretString" in secret_value:
            secret = secret_value["SecretString"]
        else:
            raise AppSettingsException("The specified secret is malformed.")

        return Settings(**json.loads(secret))
