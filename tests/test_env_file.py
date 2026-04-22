from pathlib import Path

import pytest

from redshift_user_admin.env_file import merged_environ, parse_env_file


def test_parse_export_double_quoted(tmp_path: Path) -> None:
    p = tmp_path / "e.env"
    p.write_text('export FOO="bar baz"\n')
    assert parse_env_file(p) == {"FOO": "bar baz"}


def test_parse_comment_and_blank(tmp_path: Path) -> None:
    p = tmp_path / "e.env"
    p.write_text("\n# c\nX=1\n\n")
    assert parse_env_file(p) == {"X": "1"}


def test_parse_unquoted(tmp_path: Path) -> None:
    p = tmp_path / "e.env"
    p.write_text("HOST=localhost\n")
    assert parse_env_file(p) == {"HOST": "localhost"}


def test_parse_double_quoted_escapes(tmp_path: Path) -> None:
    p = tmp_path / "e.env"
    p.write_text(r'PWD="a\"b\\c"' "\n")
    d = parse_env_file(p)
    assert d["PWD"] == 'a"b\\c'


def test_parse_unterminated_double_quoted(tmp_path: Path) -> None:
    p = tmp_path / "e.env"
    p.write_text('X="broken\n')
    with pytest.raises(ValueError, match="Unterminated"):
        parse_env_file(p)


def test_merged_environ_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("REDSHIFT_HOST", "from-process")
    p = tmp_path / "e.env"
    p.write_text("REDSHIFT_HOST=from-file\n")
    m = merged_environ(p)
    assert m["REDSHIFT_HOST"] == "from-file"


def test_merged_environ_none_is_process_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZZZ_UNIQUE", "proc")
    m = merged_environ(None)
    assert m["ZZZ_UNIQUE"] == "proc"
