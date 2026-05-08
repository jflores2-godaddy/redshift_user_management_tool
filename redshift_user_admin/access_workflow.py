from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from redshift_user_admin.db import quote_identifier

if TYPE_CHECKING:
    import redshift_connector


def schema_token(schema: str) -> str | None:
    """Derive a lowercase token from a schema name for writer-group matching."""
    s = schema.strip().lower()
    if s.startswith("ba_"):
        s = s[3:]
    parts = [p for p in s.split("_") if p]
    if not parts:
        return None
    return parts[-1]


def recommend_writer_group(schema: str, writer_gronames: list[str]) -> str | None:
    """Pick a writer group name for the schema using token and naming conventions.

    Prefers ``<token>_writers`` (case-insensitive), then any ``*_writers`` group
    whose name contains the token.
    """
    token = schema_token(schema)
    if not token:
        return None
    lower_names = {g: g.lower() for g in writer_gronames}
    exact = f"{token}_writers"
    for g in writer_gronames:
        if lower_names[g] == exact:
            return g
    candidates = [g for g in writer_gronames if lower_names[g].endswith("_writers")]
    for g in sorted(candidates, key=len, reverse=True):
        if token in lower_names[g]:
            return g
    return None


def writer_groups_matching_schema(schema: str, writer_gronames: list[str]) -> list[str]:
    """Writer groups whose name plausibly relates to the schema (for highlighting)."""
    token = schema_token(schema)
    if not token:
        return []
    return sorted(g for g in writer_gronames if token in g.lower())


def pick_sample_tables(rows: list[tuple[str, str]], limit: int = 3) -> list[tuple[str, str]]:
    """Pick up to ``limit`` (tablename, tableowner), preferring distinct owners first."""
    if not rows:
        return []
    picked: list[tuple[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    owners_order: list[str] = []

    for tab, own in rows:
        if len(picked) >= limit:
            break
        if own not in owners_order:
            picked.append((tab, own))
            seen_pairs.add((tab, own))
            owners_order.append(own)

    for tab, own in rows:
        if len(picked) >= limit:
            break
        if (tab, own) not in seen_pairs:
            picked.append((tab, own))
            seen_pairs.add((tab, own))

    return picked[:limit]


def _format_params_for_log(params: tuple | list | None) -> str:
    if not params:
        return ""
    return " | params: " + repr(tuple(params))


def log_sql(sql: str, params: tuple | list | None = None) -> None:
    """Print SQL (and params) to stdout before execution."""
    print(f"-- SQL{_format_params_for_log(params)}")
    print(sql.rstrip())
    if params:
        print(f"-- (execute with {len(params)} parameter(s))")


def log_and_execute(
    conn: "redshift_connector.Connection",
    sql: str,
    params: tuple | list | None = None,
    *,
    dry_run: bool = False,
) -> None:
    """Log SQL to stdout, then execute and commit unless ``dry_run``."""
    log_sql(sql, params)
    if dry_run:
        return
    cur = conn.cursor()
    if params is not None:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    conn.commit()


def _now_utc_naive() -> datetime:
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)


def password_expired(valuntil: datetime | None) -> bool:
    if valuntil is None:
        return False
    vu = valuntil
    if vu.tzinfo is not None:
        vu = vu.astimezone(timezone.utc).replace(tzinfo=None)
    return vu < _now_utc_naive()


@dataclass(frozen=True)
class TablePrivilegeRow:
    table: str
    owner: str
    can_insert: bool
    can_select: bool


@dataclass(frozen=True)
class InvestigateReport:
    host: str
    database: str
    default_group: str
    username: str
    schema: str
    user_found: bool
    usename: str | None
    usesysid: int | None
    usesuper: bool | None
    valuntil: datetime | None
    password_expired_flag: bool | None
    member_groups: tuple[str, ...]
    writer_groups: tuple[str, ...]
    recommended_writer: str | None
    writer_groups_highlighted: tuple[str, ...]
    schema_found: bool
    schema_owner: str | None
    sample_tables: tuple[tuple[str, str], ...]
    table_privileges: tuple[TablePrivilegeRow, ...]
    target_error: str | None = None


def run_investigate(
    conn: "redshift_connector.Connection",
    *,
    username: str,
    schema: str,
    default_group: str,
    host: str,
    database: str,
) -> InvestigateReport:
    """Run read-only investigation queries and return structured results."""
    cur = conn.cursor()

    sql_user = (
        "SELECT usename, usesysid, usesuper, valuntil "
        "FROM pg_user WHERE usename = %s"
    )
    log_sql(sql_user, (username,))
    cur.execute(sql_user, (username,))
    urow = cur.fetchone()

    sql_writers = (
        "SELECT groname FROM pg_group WHERE groname ILIKE %s ORDER BY groname"
    )
    writer_pat = "%writer%"
    log_sql(sql_writers, (writer_pat,))
    cur.execute(sql_writers, (writer_pat,))
    writer_groups = tuple(r[0] for r in cur.fetchall() if r[0])
    rec = recommend_writer_group(schema, list(writer_groups))
    highlighted = tuple(writer_groups_matching_schema(schema, list(writer_groups)))

    sql_schema = (
        "SELECT n.nspname AS schema_name, u.usename AS schema_owner "
        "FROM pg_namespace n "
        "JOIN pg_user u ON n.nspowner = u.usesysid "
        "WHERE n.nspname = %s"
    )
    log_sql(sql_schema, (schema,))
    cur.execute(sql_schema, (schema,))
    srow = cur.fetchone()
    schema_found = srow is not None
    schema_owner = str(srow[1]) if srow else None

    sample_tables: list[tuple[str, str]] = []
    priv_rows: list[TablePrivilegeRow] = []
    if schema_found:
        sql_tables = (
            "SELECT tablename, tableowner FROM pg_tables "
            "WHERE schemaname = %s ORDER BY tablename"
        )
        log_sql(sql_tables, (schema,))
        cur.execute(sql_tables, (schema,))
        all_tables = [(r[0], r[1]) for r in cur.fetchall()]
        sample_tables = pick_sample_tables(all_tables, 3)

    if urow is None:
        return InvestigateReport(
            host=host,
            database=database,
            default_group=default_group,
            username=username,
            schema=schema,
            user_found=False,
            usename=None,
            usesysid=None,
            usesuper=None,
            valuntil=None,
            password_expired_flag=None,
            member_groups=(),
            writer_groups=writer_groups,
            recommended_writer=rec,
            writer_groups_highlighted=highlighted,
            schema_found=schema_found,
            schema_owner=schema_owner,
            sample_tables=tuple(sample_tables),
            table_privileges=(),
        )

    usename, usesysid, usesuper, valuntil = urow[0], urow[1], bool(urow[2]), urow[3]
    expired = password_expired(valuntil)

    sql_groups = (
        "SELECT u.usename, g.groname "
        "FROM pg_user u "
        "JOIN pg_group g ON u.usesysid = ANY(g.grolist) "
        "WHERE u.usename = %s "
        "ORDER BY g.groname"
    )
    log_sql(sql_groups, (username,))
    cur.execute(sql_groups, (username,))
    member_groups = tuple(sorted({r[1] for r in cur.fetchall() if r[1]}))

    if schema_found and sample_tables:
        for tab, owner in sample_tables:
            fq = f"{quote_identifier(schema)}.{quote_identifier(tab)}"
            sql_priv = (
                "SELECT "
                "HAS_TABLE_PRIVILEGE(%s, %s, 'INSERT') AS can_insert, "
                "HAS_TABLE_PRIVILEGE(%s, %s, 'SELECT') AS can_select"
            )
            params = (username, fq, username, fq)
            log_sql(sql_priv, params)
            cur.execute(sql_priv, params)
            prow = cur.fetchone()
            if prow:
                priv_rows.append(
                    TablePrivilegeRow(
                        table=tab,
                        owner=owner,
                        can_insert=bool(prow[0]),
                        can_select=bool(prow[1]),
                    )
                )

    return InvestigateReport(
        host=host,
        database=database,
        default_group=default_group,
        username=username,
        schema=schema,
        user_found=True,
        usename=usename,
        usesysid=usesysid,
        usesuper=usesuper,
        valuntil=valuntil,
        password_expired_flag=expired,
        member_groups=member_groups,
        writer_groups=writer_groups,
        recommended_writer=rec,
        writer_groups_highlighted=highlighted,
        schema_found=schema_found,
        schema_owner=schema_owner,
        sample_tables=tuple(sample_tables),
        table_privileges=tuple(priv_rows),
    )


def summarize_investigate(rep: InvestigateReport) -> dict[str, str | bool]:
    """Build summary flags for display."""
    has_read = rep.default_group in rep.member_groups if rep.user_found else False
    rec = rep.recommended_writer
    in_rec_writer = bool(rec and rec in rep.member_groups)
    has_insert = any(p.can_insert for p in rep.table_privileges)
    has_write = (in_rec_writer or has_insert) if rep.user_found else False
    return {
        "user_exists": rep.user_found,
        "password_expired": bool(rep.password_expired_flag),
        "has_read": has_read,
        "has_write": has_write,
        "in_recommended_writer": in_rec_writer,
    }


def is_user_in_group(
    conn: "redshift_connector.Connection", *, username: str, group_name: str
) -> bool:
    cur = conn.cursor()
    sql = (
        "SELECT 1 FROM pg_user u "
        "JOIN pg_group g ON u.usesysid = ANY(g.grolist) "
        "WHERE u.usename = %s AND g.groname = %s"
    )
    log_sql(sql, (username, group_name))
    cur.execute(sql, (username, group_name))
    return cur.fetchone() is not None


def group_exists(conn: "redshift_connector.Connection", group_name: str) -> bool:
    cur = conn.cursor()
    sql = "SELECT 1 FROM pg_group WHERE groname = %s"
    log_sql(sql, (group_name,))
    cur.execute(sql, (group_name,))
    return cur.fetchone() is not None


def grant_read_access(
    conn: "redshift_connector.Connection",
    *,
    username: str,
    default_group: str,
    dry_run: bool,
) -> None:
    if is_user_in_group(conn, username=username, group_name=default_group):
        print(
            f"-- SKIP: user already in group {default_group!r} "
            f"(ALTER GROUP not executed)"
        )
        return
    g = quote_identifier(default_group)
    u = quote_identifier(username)
    sql = f"ALTER GROUP {g} ADD USER {u}"
    log_and_execute(conn, sql, dry_run=dry_run)


def grant_write_access(
    conn: "redshift_connector.Connection",
    *,
    username: str,
    schema: str,
    writer_group: str,
    dry_run: bool,
) -> None:
    if not is_user_in_group(conn, username=username, group_name=writer_group):
        g = quote_identifier(writer_group)
        u = quote_identifier(username)
        sql = f"ALTER GROUP {g} ADD USER {u}"
        log_and_execute(conn, sql, dry_run=dry_run)
    else:
        print(
            f"-- SKIP: user already in group {writer_group!r} "
            f"(ALTER GROUP not executed)"
        )

    sg = quote_identifier(schema)
    wg = quote_identifier(writer_group)
    sql_usage = f"GRANT USAGE ON SCHEMA {sg} TO GROUP {wg}"
    log_and_execute(conn, sql_usage, dry_run=dry_run)

    sql_tables = (
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {sg} TO GROUP {wg}"
    )
    log_and_execute(conn, sql_tables, dry_run=dry_run)


def resolve_writer_group(
    conn: "redshift_connector.Connection",
    *,
    schema: str,
    writer_group_override: str | None,
) -> str:
    """Return writer group name, using override or DB-driven recommendation."""
    if writer_group_override:
        return writer_group_override
    cur = conn.cursor()
    sql = "SELECT groname FROM pg_group WHERE groname ILIKE %s ORDER BY groname"
    log_sql(sql, ("%writer%",))
    cur.execute(sql, ("%writer%",))
    writer_groups = [r[0] for r in cur.fetchall() if r[0]]
    rec = recommend_writer_group(schema, writer_groups)
    if rec is None:
        raise ValueError(
            "Could not infer a writer group from the schema name. "
            "Pass --writer-group explicitly."
        )
    return rec
