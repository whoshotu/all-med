import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse


class ConfigError(Exception):
    pass


@dataclass
class CalleConfig:
    api_key: str
    base_url: Optional[str] = None


def load_calle_config() -> CalleConfig:
    api_key = os.environ.get("CALLE_API_KEY")
    base_url = os.environ.get("CALLE_BASE_URL") or os.environ.get("CALLE_API_BASE_URL")

    if not api_key:
        raise ConfigError("CALLE_API_KEY is not set")

    if base_url:
        base_url = base_url.rstrip("/")
        parsed = urlparse(base_url)
        # Require HTTPS for all non-localhost origins so the API key is never
        # transmitted over a plaintext connection.
        is_localhost = parsed.hostname in ("localhost", "127.0.0.1", "::1")
        if not is_localhost and parsed.scheme != "https":
            raise ConfigError(
                f"CALLE_BASE_URL must use https:// for non-localhost origins "
                f"(got '{parsed.scheme}://'). Sending API credentials over plain "
                f"HTTP is not permitted."
            )

    return CalleConfig(api_key=api_key, base_url=base_url)
