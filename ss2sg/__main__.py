from pprint import pprint

# from pydantic import BaseSettings

# from .akamai import AkamaiClient, AkamaiSettings
from .aws import work


# class Settings(BaseSettings):
#     akamai_settings: AkamaiSettings = AkamaiSettings()


if __name__ == "__main__":
    # settings = Settings()
    # c = AkamaiClient(settings.akamai_settings)
    # pprint(c.list_maps())
    work()
