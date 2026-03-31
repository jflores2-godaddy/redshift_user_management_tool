from __future__ import annotations

import re
from datetime import datetime, timezone

import redshift_connector
from dateutil.relativedelta import relativedelta

from redshift_user_admin.db import fetch_user_info, reset_user_password, set_valid_until
from redshift_user_admin.models import RecoveryResult, UserInfo
from redshift_user_admin.passwords import generate_password

VALID_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")


class UserNotFoundError(Exception):
    pass


def validate_username(username: str) -> str:
    """Validate a Redshift username against allowed pattern.

    Raises ValueError if the username is invalid.
    """
    if not VALID_USERNAME_RE.match(username):
        raise ValueError(
            f"Invalid username {username!r}. "
            "Must start with a letter, contain only letters/digits/underscores, "
            "and be 1-63 characters long."
        )
    return username


def get_user_info(conn: redshift_connector.Connection, username: str) -> UserInfo:
    """Fetch user info after validating the username.

    Raises UserNotFoundError if the user does not exist.
    """
    validate_username(username)
    info = fetch_user_info(conn, username)
    if info is None:
        raise UserNotFoundError(f"User {username!r} does not exist in Redshift.")
    return info


def compute_new_valid_until(current_valid_until: datetime | None) -> datetime:
    """Compute a new VALID UNTIL date extended by 6 calendar months.

    Uses max(current_valid_until, now) as the base if current_valid_until
    exists; otherwise uses now.
    """
    now = datetime.now(tz=timezone.utc)

    if current_valid_until is not None:
        base = current_valid_until if current_valid_until.tzinfo else current_valid_until.replace(tzinfo=timezone.utc)
        if base < now:
            base = now
    else:
        base = now

    return base + relativedelta(months=6)


def recover_user(conn: redshift_connector.Connection, username: str) -> RecoveryResult:
    """Recover a Redshift user account: reset password and extend validity.

    Performs the password reset and VALID UNTIL update within a single
    logical transaction (both committed together).
    """
    info = get_user_info(conn, username)
    new_valid_until = compute_new_valid_until(info.valid_until)
    password = generate_password()

    reset_user_password(conn, username, password)
    set_valid_until(conn, username, new_valid_until)

    return RecoveryResult(
        username=info.username,
        previous_valid_until=info.valid_until,
        new_valid_until=new_valid_until,
        temporary_password=password,
    )
