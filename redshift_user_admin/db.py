from __future__ import annotations

from datetime import datetime

import redshift_connector

from redshift_user_admin.config import RedshiftConfig
from redshift_user_admin.models import UserInfo


def get_connection(config: RedshiftConfig) -> redshift_connector.Connection:
    """Create a new Redshift connection from the given config."""
    return redshift_connector.connect(
        host=config.host,
        port=config.port,
        database=config.database,
        user=config.admin_user,
        password=config.admin_password,
        ssl=config.ssl,
    )


def fetch_user_info(conn: redshift_connector.Connection, username: str) -> UserInfo | None:
    """Query pg_user for the given username. Returns None if not found."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT usename, valuntil FROM pg_user WHERE usename = %s",
        (username,),
    )
    row = cursor.fetchone()
    if row is None:
        return None

    valid_until: datetime | None = row[1]
    return UserInfo(username=row[0], valid_until=valid_until)


def _quote_identifier(name: str) -> str:
    """Double-quote a SQL identifier, escaping any embedded double quotes."""
    return '"' + name.replace('"', '""') + '"'


def _escape_password(password: str) -> str:
    """Escape a password for use in a SQL string literal (single-quote delimited)."""
    return password.replace("'", "''")


def reset_user_password(conn: redshift_connector.Connection, username: str, password: str) -> None:
    """Change the password for the given Redshift user."""
    safe_user = _quote_identifier(username)
    safe_pass = _escape_password(password)
    conn.cursor().execute(f"ALTER USER {safe_user} PASSWORD '{safe_pass}'")
    conn.commit()


def set_valid_until(conn: redshift_connector.Connection, username: str, valid_until: datetime) -> None:
    """Set the VALID UNTIL timestamp for the given Redshift user."""
    safe_user = _quote_identifier(username)
    ts = valid_until.strftime("%Y-%m-%d %H:%M:%S")
    conn.cursor().execute(f"ALTER USER {safe_user} VALID UNTIL '{ts}'")
    conn.commit()
