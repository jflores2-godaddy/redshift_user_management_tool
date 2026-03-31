from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RedshiftConfig:
    host: str
    database: str
    admin_user: str
    admin_password: str
    port: int = 5439
    ssl: bool = True


def load_config() -> RedshiftConfig:
    """Load Redshift connection configuration from environment variables.

    Required:
        REDSHIFT_HOST, REDSHIFT_DATABASE, REDSHIFT_ADMIN_USER, REDSHIFT_ADMIN_PASSWORD

    Optional:
        REDSHIFT_PORT (default 5439), REDSHIFT_SSL (default true)
    """
    required = {
        "REDSHIFT_HOST": "host",
        "REDSHIFT_DATABASE": "database",
        "REDSHIFT_ADMIN_USER": "admin_user",
        "REDSHIFT_ADMIN_PASSWORD": "admin_password",
    }

    missing = [var for var in required if not os.environ.get(var)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    port_raw = os.environ.get("REDSHIFT_PORT", "5439")
    try:
        port = int(port_raw)
    except ValueError:
        raise EnvironmentError(
            f"REDSHIFT_PORT must be an integer, got: {port_raw!r}"
        )

    ssl_raw = os.environ.get("REDSHIFT_SSL", "true").lower()
    ssl = ssl_raw in ("true", "1", "yes")

    return RedshiftConfig(
        host=os.environ["REDSHIFT_HOST"],
        database=os.environ["REDSHIFT_DATABASE"],
        admin_user=os.environ["REDSHIFT_ADMIN_USER"],
        admin_password=os.environ["REDSHIFT_ADMIN_PASSWORD"],
        port=port,
        ssl=ssl,
    )
