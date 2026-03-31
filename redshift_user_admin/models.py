from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class UserInfo:
    username: str
    valid_until: datetime | None


@dataclass(frozen=True)
class RecoveryResult:
    username: str
    previous_valid_until: datetime | None
    new_valid_until: datetime
    temporary_password: str
