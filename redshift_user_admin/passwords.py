from __future__ import annotations

import secrets
import string

UPPERCASE = string.ascii_uppercase
LOWERCASE = string.ascii_lowercase
DIGITS = string.digits
# SQL-safe symbols: excludes single quote, double quote, and backslash
SYMBOLS = "!@#$%^&*()-_=+[]{};:,.<>?/|`~"

ALPHABET = UPPERCASE + LOWERCASE + DIGITS + SYMBOLS


def _meets_requirements(password: str) -> bool:
    return (
        any(c in UPPERCASE for c in password)
        and any(c in LOWERCASE for c in password)
        and any(c in DIGITS for c in password)
        and any(c in SYMBOLS for c in password)
    )


def generate_password(length: int = 16) -> str:
    """Generate a cryptographically secure password.

    Guarantees at least one uppercase, one lowercase, one digit, and one
    SQL-safe symbol. Never contains single quotes, double quotes, or
    backslashes.
    """
    if length < 4:
        raise ValueError("Password length must be at least 4")

    while True:
        password = "".join(secrets.choice(ALPHABET) for _ in range(length))
        if _meets_requirements(password):
            return password
