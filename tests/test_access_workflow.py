"""Tests for access investigation helpers (no live Redshift)."""

from datetime import datetime, timezone


from redshift_user_admin.access_workflow import (
    InvestigateReport,
    TablePrivilegeRow,
    pick_sample_tables,
    recommend_writer_group,
    summarize_investigate,
    writer_groups_matching_schema,
)


class TestRecommendWriterGroup:
    def test_ba_ecommerce_prefers_ecommerce_writers(self) -> None:
        writers = ["ecommerce_writers", "marketing_writers", "finance_writers"]
        assert recommend_writer_group("ba_ecommerce", writers) == "ecommerce_writers"

    def test_returns_none_when_no_match(self) -> None:
        writers = ["marketing_writers", "finance_writers"]
        assert recommend_writer_group("ba_ecommerce", writers) is None

    def test_contains_token_fallback(self) -> None:
        writers = ["foo_ecommerce_bar_writers"]
        assert recommend_writer_group("ba_ecommerce", writers) == "foo_ecommerce_bar_writers"


class TestWriterGroupsMatchingSchema:
    def test_highlights_containing_token(self) -> None:
        writers = ["ecommerce_writers", "marketing_writers", "ecommerce_special_writers"]
        assert writer_groups_matching_schema("ba_ecommerce", writers) == [
            "ecommerce_special_writers",
            "ecommerce_writers",
        ]


class TestPickSampleTables:
    def test_prefers_distinct_owners(self) -> None:
        rows = [
            ("a", "o1"),
            ("b", "o1"),
            ("c", "o2"),
            ("d", "o3"),
        ]
        picked = pick_sample_tables(rows, 3)
        owners = [p[1] for p in picked]
        assert len(picked) == 3
        assert len(set(owners)) == 3

    def test_empty(self) -> None:
        assert pick_sample_tables([], 3) == []


class TestSummarizeInvestigate:
    def test_read_and_write_flags(self) -> None:
        rep = InvestigateReport(
            host="h",
            database="d",
            default_group="readers",
            username="u",
            schema="ba_ecommerce",
            user_found=True,
            usename="u",
            usesysid=1,
            usesuper=False,
            valuntil=datetime(2099, 1, 1, tzinfo=timezone.utc),
            password_expired_flag=False,
            member_groups=("readers", "ecommerce_writers"),
            writer_groups=("ecommerce_writers",),
            recommended_writer="ecommerce_writers",
            writer_groups_highlighted=("ecommerce_writers",),
            schema_found=True,
            schema_owner="owner",
            sample_tables=(("t1", "o1"),),
            table_privileges=(
                TablePrivilegeRow("t1", "o1", can_insert=True, can_select=True),
            ),
        )
        s = summarize_investigate(rep)
        assert s["user_exists"] is True
        assert s["has_read"] is True
        assert s["has_write"] is True

    def test_user_not_found(self) -> None:
        rep = InvestigateReport(
            host="h",
            database="d",
            default_group="readers",
            username="u",
            schema="s",
            user_found=False,
            usename=None,
            usesysid=None,
            usesuper=None,
            valuntil=None,
            password_expired_flag=None,
            member_groups=(),
            writer_groups=(),
            recommended_writer=None,
            writer_groups_highlighted=(),
            schema_found=False,
            schema_owner=None,
            sample_tables=(),
            table_privileges=(),
        )
        s = summarize_investigate(rep)
        assert s["has_read"] is False
        assert s["has_write"] is False
