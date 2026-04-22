from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

_DEFAULT_GROUP = "analytics_general_readers"
_VALID_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")


def _validate_default_group(name: str) -> str:
    if not _VALID_IDENTIFIER.match(name):
        raise EnvironmentError(
            f"Invalid REDSHIFT_DEFAULT_GROUP {name!r}. "
            "Must start with a letter, contain only letters/digits/underscores, "
            "and be 1-63 characters long."
        )
    return name


@dataclass(frozen=True)
class RedshiftConfig:
    host: str
    database: str
    admin_user: str
    admin_password: str
    port: int = 5439
    ssl: bool = True
    default_group: str = _DEFAULT_GROUP


def load_config(environ: Mapping[str, str] | None = None) -> RedshiftConfig:
    """Load Redshift connection configuration from environment variables.

    Required:
        REDSHIFT_HOST, REDSHIFT_DATABASE, REDSHIFT_ADMIN_USER, REDSHIFT_ADMIN_PASSWORD

    Optional:
        REDSHIFT_PORT (default 5439), REDSHIFT_SSL (default true),
        REDSHIFT_DEFAULT_GROUP (default analytics_general_readers)

    Args:
        environ: If provided, read from this mapping instead of ``os.environ``.
    """
    env = os.environ if environ is None else environ
    required = {
        "REDSHIFT_HOST": "host",
        "REDSHIFT_DATABASE": "database",
        "REDSHIFT_ADMIN_USER": "admin_user",
        "REDSHIFT_ADMIN_PASSWORD": "admin_password",
    }

    missing = [var for var in required if not env.get(var)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    port_raw = env.get("REDSHIFT_PORT", "5439")
    try:
        port = int(port_raw)
    except ValueError:
        raise EnvironmentError(
            f"REDSHIFT_PORT must be an integer, got: {port_raw!r}"
        )

    ssl_raw = env.get("REDSHIFT_SSL", "true").lower()
    ssl = ssl_raw in ("true", "1", "yes")

    default_group = _validate_default_group(
        env.get("REDSHIFT_DEFAULT_GROUP", _DEFAULT_GROUP)
    )

    return RedshiftConfig(
        host=env["REDSHIFT_HOST"],
        database=env["REDSHIFT_DATABASE"],
        admin_user=env["REDSHIFT_ADMIN_USER"],
        admin_password=env["REDSHIFT_ADMIN_PASSWORD"],
        port=port,
        ssl=ssl,
        default_group=default_group,
    )
