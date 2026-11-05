"""Small dependency-free structured logging setup."""

import json
import logging
import re
from datetime import datetime, timezone

_SENSITIVE_VALUE = re.compile(
    r"(?i)\b(password|passwd|secret|api[_-]?key|authorization|bearer|token)\b"
    r"(\s*[:=]\s*)([^\s,;]+)"
)


def redact_message(message: str) -> str:
    """Remove common secret-shaped values before they reach a log sink."""

    return _SENSITIVE_VALUE.sub(r"\1\2[REDACTED]", message)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": redact_message(record.getMessage()),
            },
            ensure_ascii=False,
        )


def configure_logging() -> None:
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)
    root.setLevel(logging.INFO)
