import pytest

from redshift_user_admin.service import validate_group_name, validate_username


class TestValidateUsername:
    @pytest.mark.parametrize(
        "username",
        [
            "alice",
            "user_123",
            "A",
            "a" * 63,
            "Admin_User_01",
            "z0_",
        ],
    )
    def test_valid_usernames(self, username: str) -> None:
        assert validate_username(username) == username

    @pytest.mark.parametrize(
        "username,reason",
        [
            ("", "empty string"),
            ("1user", "starts with digit"),
            ("_user", "starts with underscore"),
            ("user name", "contains space"),
            ("user-name", "contains hyphen"),
            ("user@name", "contains at sign"),
            ("user.name", "contains dot"),
            ("a" * 64, "too long (64 chars)"),
            ("'; DROP TABLE users;--", "SQL injection attempt"),
            ('user"name', "contains double quote"),
        ],
    )
    def test_invalid_usernames(self, username: str, reason: str) -> None:
        with pytest.raises(ValueError):
            validate_username(username)


class TestValidateGroupName:
    def test_valid(self) -> None:
        assert validate_group_name("analytics_general_readers") == "analytics_general_readers"

    def test_invalid(self) -> None:
        with pytest.raises(ValueError):
            validate_group_name("bad-group")
