from __future__ import annotations

import re
from datetime import datetime, timezone

import redshift_connector
from dateutil.relativedelta import relativedelta

from redshift_user_admin.db import (
    add_user_to_group,
    create_user,
    fetch_user_info,
    reset_user_password,
    set_valid_until,
)
from redshift_user_admin.models import CreateUserResult, RecoveryResult, UserInfo
from redshift_user_admin.passwords import generate_password

VALID_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")


class UserNotFoundError(Exception):
    pass


class UserAlreadyExistsError(Exception):
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


def validate_group_name(name: str) -> str:
    """Validate a Redshift group name (same rules as usernames)."""
    if not VALID_USERNAME_RE.match(name):
        raise ValueError(
            f"Invalid group name {name!r}. "
            "Must start with a letter, contain only letters/digits/underscores, "
            "and be 1-63 characters long."
        )
    return name


def ensure_user_absent(conn: redshift_connector.Connection, username: str) -> None:
    """Ensure the login does not exist; raises UserAlreadyExistsError if it does."""
    validate_username(username)
    if fetch_user_info(conn, username) is not None:
        raise UserAlreadyExistsError(
            f"User {username!r} already exists in Redshift on this target."
        )


def get_user_info(conn: redshift_connector.Connection, username: str) -> UserInfo:
    """Fetch user info after validating the username.

    Raises UserNotFoundError if the user does not exist.
    """
    validate_username(username)
    info = fetch_user_info(conn, username)
    if info is None:
        raise UserNotFoundError(f"User {username!r} does not exist in Redshift.")
    return info


def compute_new_valid_until() -> datetime:
    """Compute VALID UNTIL as UTC now plus 6 calendar months."""
    now = datetime.now(tz=timezone.utc)
    return now + relativedelta(months=6)


def recover_user(
    conn: redshift_connector.Connection,
    username: str,
    *,
    password: str | None = None,
    new_valid_until: datetime | None = None,
) -> RecoveryResult:
    """Recover a Redshift user account: reset password and extend validity.

    New expiry is always anchored from UTC now (+6 months), not from the
    previous VALID UNTIL. Optional ``password`` and ``new_valid_until`` allow
    applying the same values across multiple clusters.

    Performs the password reset and VALID UNTIL update within a single
    logical transaction (both committed together).
    """
    info = get_user_info(conn, username)
    vu = new_valid_until if new_valid_until is not None else compute_new_valid_until()
    pwd = password if password is not None else generate_password()

    reset_user_password(conn, username, pwd)
    set_valid_until(conn, username, vu)

    return RecoveryResult(
        username=info.username,
        previous_valid_until=info.valid_until,
        new_valid_until=vu,
        temporary_password=pwd,
    )


def create_user_account(
    conn: redshift_connector.Connection,
    username: str,
    default_group: str,
    password: str | None = None,
    valid_until: datetime | None = None,
) -> CreateUserResult:
    """Create a Redshift user, add to group, with optional fixed password/expiry."""
    validate_username(username)
    validate_group_name(default_group)
    if fetch_user_info(conn, username) is not None:
        raise UserAlreadyExistsError(
            f"User {username!r} already exists in Redshift on this target."
        )
    if password is None:
        password = generate_password()
    if valid_until is None:
        valid_until = compute_new_valid_until()

    create_user(conn, username, password, valid_until)
    add_user_to_group(conn, default_group, username)

    return CreateUserResult(
        username=username,
        temporary_password=password,
        valid_until=valid_until,
        default_group=default_group,
    )
