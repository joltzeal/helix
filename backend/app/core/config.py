from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Helix"
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    api_reload: bool = True

    bitbrowser_base_url: str = Field(
        default="http://127.0.0.1:54345",
        description="BitBrowser Local Server base URL.",
    )
    bitbrowser_timeout_seconds: float = 30.0
    cloud_mail_base_url: str = Field(
        default="",
        description="CloudMail API base URL, for example https://mail.example.com.",
    )
    cloud_mail_email: str = Field(
        default="",
        description="CloudMail administrator email used to generate API token.",
    )
    cloud_mail_password: str = Field(
        default="",
        description="CloudMail administrator password used to generate API token.",
    )
    cloud_mail_timeout_seconds: float = 30.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="UCARD_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
