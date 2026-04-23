from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from redshift_user_admin.service import compute_new_valid_until


FIXED_NOW = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _freeze_time():
    with patch("redshift_user_admin.service.datetime") as mock_dt:
        mock_dt.now.return_value = FIXED_NOW
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        yield


class TestComputeNewValidUntil:
    def test_always_extends_from_utc_now(self) -> None:
        result = compute_new_valid_until()
        assert result == datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)

    def test_calendar_month_end_handling(self) -> None:
        """Aug 31 + 6 months = Feb 28 (non-leap year)."""
        aug_31 = datetime(2026, 8, 31, 23, 59, 59, tzinfo=timezone.utc)
        with patch("redshift_user_admin.service.datetime") as mock_dt:
            mock_dt.now.return_value = aug_31
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = compute_new_valid_until()
        assert result == datetime(2027, 2, 28, 23, 59, 59, tzinfo=timezone.utc)
