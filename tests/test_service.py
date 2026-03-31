from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from redshift_user_admin.models import UserInfo
from redshift_user_admin.service import (
    UserNotFoundError,
    get_user_info,
    recover_user,
)


class TestGetUserInfo:
    def test_returns_user_when_found(self) -> None:
        conn = MagicMock()
        expected = UserInfo(username="alice", valid_until=datetime(2026, 6, 1, tzinfo=timezone.utc))
        with patch("redshift_user_admin.service.fetch_user_info", return_value=expected):
            result = get_user_info(conn, "alice")
        assert result == expected

    def test_raises_when_user_not_found(self) -> None:
        conn = MagicMock()
        with patch("redshift_user_admin.service.fetch_user_info", return_value=None):
            with pytest.raises(UserNotFoundError, match="alice"):
                get_user_info(conn, "alice")

    def test_raises_on_invalid_username(self) -> None:
        conn = MagicMock()
        with pytest.raises(ValueError):
            get_user_info(conn, "1bad")


class TestRecoverUser:
    @patch("redshift_user_admin.service.set_valid_until")
    @patch("redshift_user_admin.service.reset_user_password")
    @patch("redshift_user_admin.service.generate_password", return_value="T3st!Pass_word1")
    @patch("redshift_user_admin.service.fetch_user_info")
    def test_full_recovery_flow(
        self, mock_fetch, mock_gen_pw, mock_reset_pw, mock_set_vu
    ) -> None:
        conn = MagicMock()
        valid_until = datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc)
        mock_fetch.return_value = UserInfo(username="bob", valid_until=valid_until)

        result = recover_user(conn, "bob")

        assert result.username == "bob"
        assert result.previous_valid_until == valid_until
        assert result.temporary_password == "T3st!Pass_word1"
        mock_reset_pw.assert_called_once_with(conn, "bob", "T3st!Pass_word1")
        mock_set_vu.assert_called_once_with(conn, "bob", result.new_valid_until)

    @patch("redshift_user_admin.service.fetch_user_info", return_value=None)
    def test_recover_raises_when_user_not_found(self, mock_fetch) -> None:
        conn = MagicMock()
        with pytest.raises(UserNotFoundError):
            recover_user(conn, "ghost")
