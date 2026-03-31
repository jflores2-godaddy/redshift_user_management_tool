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
    def test_future_valid_until_extends_from_that_date(self) -> None:
        future = datetime(2026, 8, 15, 0, 0, 0, tzinfo=timezone.utc)
        result = compute_new_valid_until(future)
        assert result == datetime(2027, 2, 15, 0, 0, 0, tzinfo=timezone.utc)

    def test_past_valid_until_extends_from_now(self) -> None:
        past = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = compute_new_valid_until(past)
        assert result == datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)

    def test_none_extends_from_now(self) -> None:
        result = compute_new_valid_until(None)
        assert result == datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)

    def test_calendar_month_end_handling(self) -> None:
        """Aug 31 + 6 months = Feb 28 (non-leap year)."""
        aug_31 = datetime(2026, 8, 31, 23, 59, 59, tzinfo=timezone.utc)
        result = compute_new_valid_until(aug_31)
        assert result == datetime(2027, 2, 28, 23, 59, 59, tzinfo=timezone.utc)

    def test_naive_datetime_treated_as_utc(self) -> None:
        future_naive = datetime(2026, 8, 15, 0, 0, 0)
        result = compute_new_valid_until(future_naive)
        assert result == datetime(2027, 2, 15, 0, 0, 0, tzinfo=timezone.utc)
