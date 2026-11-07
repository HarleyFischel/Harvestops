"""Safe build and runtime identity metadata."""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass

_SAFE_VALUE = re.compile(r"^[A-Za-z0-9._:/@+-]{1,160}$")


@dataclass(frozen=True)
class BuildInfo:
    version: str
    source_commit: str
    build_timestamp_utc: str
    environment: str
    image_digest: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _safe_env(name: str, default: str = "Unknown") -> str:
    value = os.getenv(name, default).strip()
    return value if value and _SAFE_VALUE.fullmatch(value) else default


def get_build_info() -> BuildInfo:
    return BuildInfo(
        version=_safe_env("HARVESTOPS_VERSION", "0.1.0"),
        source_commit=_safe_env("HARVESTOPS_COMMIT"),
        build_timestamp_utc=_safe_env("HARVESTOPS_BUILD_TIMESTAMP"),
        environment=_safe_env("HARVESTOPS_ENVIRONMENT", "development"),
        image_digest=_safe_env("HARVESTOPS_IMAGE_DIGEST"),
    )
