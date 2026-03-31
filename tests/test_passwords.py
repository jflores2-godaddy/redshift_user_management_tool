import string

import pytest

from redshift_user_admin.passwords import SYMBOLS, generate_password


class TestGeneratePassword:
    def test_default_length(self) -> None:
        pw = generate_password()
        assert len(pw) == 16

    @pytest.mark.parametrize("length", [4, 8, 14, 16, 32])
    def test_requested_length(self, length: int) -> None:
        pw = generate_password(length=length)
        assert len(pw) == length

    def test_contains_uppercase(self) -> None:
        pw = generate_password()
        assert any(c in string.ascii_uppercase for c in pw)

    def test_contains_lowercase(self) -> None:
        pw = generate_password()
        assert any(c in string.ascii_lowercase for c in pw)

    def test_contains_digit(self) -> None:
        pw = generate_password()
        assert any(c in string.digits for c in pw)

    def test_contains_symbol(self) -> None:
        pw = generate_password()
        assert any(c in SYMBOLS for c in pw)

    def test_no_forbidden_characters(self) -> None:
        for _ in range(50):
            pw = generate_password()
            assert "'" not in pw
            assert '"' not in pw
            assert "\\" not in pw

    def test_uniqueness(self) -> None:
        passwords = {generate_password() for _ in range(20)}
        assert len(passwords) > 1

    def test_minimum_length_rejected(self) -> None:
        with pytest.raises(ValueError):
            generate_password(length=3)
