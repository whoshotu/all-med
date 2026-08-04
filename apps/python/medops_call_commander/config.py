import os
from dataclasses import dataclass


class ConfigError(Exception):
    pass


@dataclass
class CalleConfig:
    api_key: str
    base_url: str
    webhook_url: str


def load_calle_config() -> CalleConfig:
    api_key = os.environ.get("CALLE_API_KEY")
    base_url = os.environ.get("CALLE_BASE_URL", "https://api.heycall-e.com")
    webhook_url = os.environ.get("CALLE_WEBHOOK_URL")

    if not api_key:
        raise ConfigError("CALLE_API_KEY is not set")
    if not webhook_url:
        raise ConfigError("CALLE_WEBHOOK_URL is not set")

    return CalleConfig(
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        webhook_url=webhook_url,
    )
