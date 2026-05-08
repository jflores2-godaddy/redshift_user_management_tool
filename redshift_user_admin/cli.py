from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from redshift_user_admin.access_workflow import (
    grant_read_access,
    grant_write_access,
    group_exists,
    resolve_writer_group,
    run_investigate,
    summarize_investigate,
)
from redshift_user_admin.config import load_config
from redshift_user_admin.db import get_connection
from redshift_user_admin.env_file import merged_environ
from redshift_user_admin.models import UserInfo
from redshift_user_admin.passwords import generate_password
from redshift_user_admin.service import (
    UserAlreadyExistsError,
    UserNotFoundError,
    compute_new_valid_until,
    create_user_account,
    ensure_user_absent,
    get_user_info,
    recover_user,
    validate_group_name,
    validate_schema_name,
    validate_username,
)

app = typer.Typer(help="Redshift user account management tool.")


def _format_timestamp(dt) -> str:
    if dt is None:
        return "not set"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _print_investigate_human(rep, label: str) -> None:
    """Print a readable investigation report (SQL is already logged by queries)."""
    typer.echo()
    typer.echo(f"========== {label} ==========")
    typer.echo(f"Host: {rep.host}    Database: {rep.database}")
    typer.echo()
    typer.echo("1. USER EXISTS")
    if not rep.user_found:
        typer.echo("   User: NOT FOUND")
    else:
        typer.echo(
            f"   User: {rep.usename}    usesysid: {rep.usesysid}    usesuper: {rep.usesuper}"
        )
        typer.echo(f"   valid_until: {_format_timestamp(rep.valuntil)}")
        if rep.password_expired_flag:
            typer.echo("   Password status: EXPIRED")
        else:
            typer.echo("   Password status: valid (or no expiry set)")
    typer.echo()
    typer.echo("2. CURRENT GROUP MEMBERSHIPS")
    if not rep.user_found:
        typer.echo("   (skipped — user not found)")
    elif not rep.member_groups:
        typer.echo("   (none)")
    else:
        for g in rep.member_groups:
            typer.echo(f"   - {g}")
    typer.echo()
    typer.echo("3. WRITER GROUPS (on cluster)")
    if not rep.writer_groups:
        typer.echo("   (none matching %writer%)")
    else:
        for g in rep.writer_groups:
            mark = "  <-- matches schema" if g in rep.writer_groups_highlighted else ""
            typer.echo(f"   - {g}{mark}")
    typer.echo()
    typer.echo("4. WRITE PRIVILEGE SPOT CHECK")
    if not rep.user_found:
        typer.echo("   (skipped — user not found)")
    elif not rep.schema_found:
        typer.echo("   (skipped — schema not found)")
    elif not rep.table_privileges:
        typer.echo("   (no tables sampled or no privilege rows)")
    else:
        for row in rep.table_privileges:
            typer.echo(
                f"   Table: {rep.schema}.{row.table}    owner: {row.owner}    "
                f"INSERT={row.can_insert}    SELECT={row.can_select}"
            )
    typer.echo()
    typer.echo("5. SCHEMA OWNER")
    if not rep.schema_found:
        typer.echo(f"   Schema {rep.schema!r}: NOT FOUND")
    else:
        typer.echo(f"   schema: {rep.schema}    owner: {rep.schema_owner}")
    typer.echo()
    typer.echo("--- Summary ---")
    summ = summarize_investigate(rep)
    if summ["user_exists"]:
        typer.echo("   User exists: YES")
    else:
        typer.echo("   User exists: NO")
    if rep.user_found:
        if summ["password_expired"]:
            typer.echo("   Password: EXPIRED")
        else:
            typer.echo("   Password: not expired")
    if summ["has_read"]:
        typer.echo("   Read: OK (already in default readers group)")
    else:
        typer.echo(
            f"   Read: MISSING (not in default group {rep.default_group!r})"
            if rep.user_found
            else "   Read: MISSING (user not found)"
        )
    if summ["has_write"]:
        typer.echo("   Write: OK (recommended writer membership or INSERT on sample)")
    else:
        typer.echo(
            "   Write: MISSING (no recommended writer membership / no INSERT on samples)"
            if rep.user_found
            else "   Write: MISSING (user not found)"
        )
    if rep.recommended_writer:
        typer.echo(
            f"   Recommended writer group (heuristic): {rep.recommended_writer}"
        )
    else:
        typer.echo(
            "   Recommended writer group: none inferred — use --writer-group on grant-access"
        )


def _report_partial_grant(
    failed_index: int, targets: list[tuple[str, Path | None]]
) -> None:
    _report_partial_targets(
        failed_index,
        targets,
        "Earlier targets may already have grants applied. "
        "Check Redshift and align group/schema grants before retrying.",
    )


@app.command("investigate")
def investigate(
    username: str = typer.Argument(..., help="Redshift username to investigate"),
    schema: str = typer.Argument(..., help="Target schema name (e.g. ba_ecommerce)"),
    env_file: Annotated[
        list[Path],
        typer.Option(
            "--env-file",
            exists=True,
            readable=True,
            help="Env file per cluster. Repeat for multiple clusters (e.g. BI then serverless).",
        ),
    ] = [],
) -> None:
    """Investigate a user's groups and privileges for a schema (DBA ticket triage).

    When unsure which cluster applies, pass every candidate --env-file and compare sections.
    """
    try:
        validate_username(username)
        validate_schema_name(schema)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    targets = _create_targets(env_file)

    for label, path in targets:
        merged = merged_environ(path)
        try:
            config = load_config(merged)
        except OSError as exc:
            typer.echo(f"Configuration error ({label}): {exc}", err=True)
            raise typer.Exit(code=1)
        conn = None
        try:
            conn = get_connection(config)
            rep = run_investigate(
                conn,
                username=username,
                schema=schema,
                default_group=config.default_group,
                host=config.host,
                database=config.database,
            )
        except Exception as exc:
            typer.echo(f"Error ({label}): {exc}", err=True)
            raise typer.Exit(code=1)
        finally:
            if conn is not None:
                conn.close()
        _print_investigate_human(rep, label)


@app.command("grant-access")
def grant_access(
    username: str = typer.Argument(..., help="Redshift username"),
    schema: str = typer.Argument(..., help="Target schema name"),
    access: str = typer.Option(
        ...,
        "--access",
        help="One of: read, write, both",
    ),
    env_file: Annotated[
        list[Path],
        typer.Option(
            "--env-file",
            exists=True,
            readable=True,
            help="Env file per cluster. Repeat for multiple clusters (e.g. BI then serverless).",
        ),
    ] = [],
    writer_group: str | None = typer.Option(
        None,
        "--writer-group",
        help="Writer group name when auto-detection from schema name fails (write/both only).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print grant SQL only; do not execute ALTER/GRANT (investigation SELECTs still run).",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Grant read and/or write access; then re-run investigation for verification.

    Run ``investigate`` first when you are unsure which ``--env-file`` targets need changes.
    """
    access_norm = access.strip().lower()
    if access_norm not in ("read", "write", "both"):
        typer.echo("Error: --access must be read, write, or both.", err=True)
        raise typer.Exit(code=1)

    try:
        validate_username(username)
        validate_schema_name(schema)
        if writer_group is not None:
            validate_group_name(writer_group)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    targets = _create_targets(env_file)

    if not dry_run and not yes:
        typer.echo("This will run ALTER GROUP / GRANT on each target (SQL is always printed first).")
        if not typer.confirm("Continue?", default=False):
            typer.echo("Aborted.")
            raise typer.Exit(code=0)

    applied_labels: list[str] = []

    for idx, (label, path) in enumerate(targets):
        merged = merged_environ(path)
        try:
            config = load_config(merged)
        except OSError as exc:
            typer.echo(f"Configuration error ({label}): {exc}", err=True)
            _report_partial_grant(idx, targets)
            raise typer.Exit(code=1)

        typer.echo()
        typer.echo(f"========== GRANT: {label} ==========")
        typer.echo(f"Host: {config.host}    Database: {config.database}")

        conn = None
        try:
            conn = get_connection(config)
            rep_pre = run_investigate(
                conn,
                username=username,
                schema=schema,
                default_group=config.default_group,
                host=config.host,
                database=config.database,
            )

            if not rep_pre.user_found:
                typer.echo(
                    f"Error ({label}): User {username!r} does not exist; cannot grant.",
                    err=True,
                )
                _report_partial_grant(idx, targets)
                raise typer.Exit(code=1)
            if not rep_pre.schema_found:
                typer.echo(
                    f"Error ({label}): Schema {schema!r} does not exist; cannot grant.",
                    err=True,
                )
                _report_partial_grant(idx, targets)
                raise typer.Exit(code=1)

            if access_norm in ("read", "both"):
                typer.echo()
                typer.echo("-- Applying READ (default readers group)")
                grant_read_access(
                    conn,
                    username=username,
                    default_group=config.default_group,
                    dry_run=dry_run,
                )

            if access_norm in ("write", "both"):
                try:
                    wg = resolve_writer_group(
                        conn,
                        schema=schema,
                        writer_group_override=writer_group,
                    )
                except ValueError as exc:
                    typer.echo(f"Error ({label}): {exc}", err=True)
                    _report_partial_grant(idx, targets)
                    raise typer.Exit(code=1)
                if not group_exists(conn, wg):
                    typer.echo(
                        f"Error ({label}): Writer group {wg!r} does not exist on this cluster.",
                        err=True,
                    )
                    _report_partial_grant(idx, targets)
                    raise typer.Exit(code=1)
                typer.echo()
                typer.echo(f"-- Applying WRITE using group {wg!r}")
                grant_write_access(
                    conn,
                    username=username,
                    schema=schema,
                    writer_group=wg,
                    dry_run=dry_run,
                )

            typer.echo()
            typer.echo("--- Post-grant verification (same checks as investigate) ---")
            rep_post = run_investigate(
                conn,
                username=username,
                schema=schema,
                default_group=config.default_group,
                host=config.host,
                database=config.database,
            )
            _print_investigate_human(rep_post, f"{label} (post-grant)")
            applied_labels.append(label)
        except typer.Exit:
            raise
        except Exception as exc:
            typer.echo(
                f"Connection, investigate, or grant error ({label}): {exc}",
                err=True,
            )
            _report_partial_grant(idx, targets)
            raise typer.Exit(code=1)
        finally:
            if conn is not None:
                conn.close()

    if not dry_run:
        typer.echo()
        typer.echo(
            f"User {username} granted {access_norm} on {schema} on "
            f"{', '.join(applied_labels)}. Verified post-grant. Ticket can be closed."
        )
    else:
        typer.echo()
        typer.echo("Dry-run finished: no ALTER/GRANT was executed. Re-run without --dry-run to apply.")


@app.command()
def info(
    username: str = typer.Argument(..., help="Redshift username to look up"),
    env_file: Annotated[
        list[Path],
        typer.Option(
            "--env-file",
            exists=True,
            readable=True,
            help="Env file (KEY=value or export ...). Repeat to query the user on multiple clusters.",
        ),
    ] = [],
) -> None:
    """Show basic info for a Redshift user (one or more clusters)."""
    try:
        validate_username(username)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    targets = _create_targets(env_file)
    multi = len(targets) > 1
    any_found = False

    for label, path in targets:
        merged = merged_environ(path)
        try:
            config = load_config(merged)
        except EnvironmentError as exc:
            typer.echo(f"Configuration error ({label}): {exc}", err=True)
            raise typer.Exit(code=1)
        conn = None
        try:
            conn = get_connection(config)
            user = get_user_info(conn, username)
        except UserNotFoundError:
            if not multi:
                typer.echo(
                    f"Error: User {username!r} does not exist in Redshift.", err=True
                )
                raise typer.Exit(code=1)
            typer.echo(f"[{label}]")
            typer.echo("  User not found")
            typer.echo()
            continue
        except Exception as exc:
            typer.echo(f"Connection error ({label}): {exc}", err=True)
            raise typer.Exit(code=1)
        finally:
            if conn is not None:
                conn.close()

        any_found = True
        legacy_single = not multi and path is None
        if legacy_single:
            typer.echo("User found")
            typer.echo(f"  username:    {user.username}")
            typer.echo(f"  valid_until: {_format_timestamp(user.valid_until)}")
        else:
            typer.echo(f"[{label}]")
            typer.echo("  User found")
            typer.echo(f"    username:    {user.username}")
            typer.echo(f"    valid_until: {_format_timestamp(user.valid_until)}")
            typer.echo()

    if multi and not any_found:
        typer.echo(
            f"Error: User {username!r} was not found on any target.", err=True
        )
        raise typer.Exit(code=1)


@app.command()
def recover(
    username: str = typer.Argument(..., help="Redshift username to recover"),
    env_file: Annotated[
        list[Path],
        typer.Option(
            "--env-file",
            exists=True,
            readable=True,
            help="Env file (KEY=value or export ...). Repeat to recover the same user on multiple clusters with one password and one VALID UNTIL.",
        ),
    ] = [],
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Recover a Redshift user account: reset password and extend validity."""
    try:
        validate_username(username)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    targets = _create_targets(env_file)
    use_env_files = bool(env_file)

    if use_env_files:
        found: list[tuple[str, UserInfo]] = []
        for label, path in targets:
            merged = merged_environ(path)
            try:
                config = load_config(merged)
            except EnvironmentError as exc:
                typer.echo(f"Configuration error ({label}): {exc}", err=True)
                raise typer.Exit(code=1)
            conn = None
            try:
                conn = get_connection(config)
                user = get_user_info(conn, username)
            except UserNotFoundError:
                typer.echo(
                    f"Error ({label}): User {username!r} does not exist in Redshift.",
                    err=True,
                )
                raise typer.Exit(code=1)
            except Exception as exc:
                typer.echo(f"Connection error ({label}): {exc}", err=True)
                raise typer.Exit(code=1)
            finally:
                if conn is not None:
                    conn.close()
            found.append((label, user))

        preview_valid = compute_new_valid_until()
        typer.echo("Preflight OK — user exists on all targets.")
        typer.echo()
        for label, user in found:
            typer.echo(f"[{label}]")
            typer.echo("  User found")
            typer.echo(f"    username:            {user.username}")
            typer.echo(f"    current valid_until: {_format_timestamp(user.valid_until)}")
            typer.echo()
        typer.echo(f"  new valid_until (all targets): {_format_timestamp(preview_valid)}")
        typer.echo()
        typer.echo("This will:")
        typer.echo("  - reset password (same on every target)")
        typer.echo("  - set VALID UNTIL to 6 calendar months from now (UTC), same on every target")
        typer.echo()

        if not yes:
            confirmed = typer.confirm("Continue?", default=False)
            if not confirmed:
                typer.echo("Aborted.")
                raise typer.Exit(code=0)

        password = generate_password()
        valid_until = compute_new_valid_until()

        for idx, (label, path) in enumerate(targets):
            merged = merged_environ(path)
            config = load_config(merged)
            try:
                conn = get_connection(config)
            except Exception as exc:
                typer.echo(f"Connection error ({label}): {exc}", err=True)
                _report_partial_recover(idx, targets)
                raise typer.Exit(code=1)
            try:
                recover_user(
                    conn,
                    username,
                    password=password,
                    new_valid_until=valid_until,
                )
            except Exception as exc:
                typer.echo(f"Error during recovery ({label}): {exc}", err=True)
                _report_partial_recover(idx, targets)
                raise typer.Exit(code=1)
            finally:
                conn.close()

        typer.echo()
        typer.echo(f"Temporary password:\n  {password}")
        typer.echo()
        typer.echo("Copy it now. It will not be shown again.")
        return

    try:
        config = load_config()
        conn = get_connection(config)
    except Exception as exc:
        typer.echo(f"Connection error: {exc}", err=True)
        raise typer.Exit(code=1)

    try:
        user = get_user_info(conn, username)
    except UserNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        conn.close()
        raise typer.Exit(code=1)

    new_valid_until = compute_new_valid_until()

    typer.echo("User found")
    typer.echo(f"  username:            {user.username}")
    typer.echo(f"  current valid_until: {_format_timestamp(user.valid_until)}")
    typer.echo(f"  new valid_until:     {_format_timestamp(new_valid_until)}")
    typer.echo()
    typer.echo("This will:")
    typer.echo("  - reset password")
    typer.echo("  - set VALID UNTIL to 6 calendar months from now (UTC)")
    typer.echo()

    if not yes:
        confirmed = typer.confirm("Continue?", default=False)
        if not confirmed:
            typer.echo("Aborted.")
            conn.close()
            raise typer.Exit(code=0)

    password = generate_password()
    valid_until = compute_new_valid_until()
    try:
        result = recover_user(
            conn,
            username,
            password=password,
            new_valid_until=valid_until,
        )
    except Exception as exc:
        typer.echo(f"Error during recovery: {exc}", err=True)
        raise typer.Exit(code=1)
    finally:
        conn.close()

    typer.echo()
    typer.echo(f"Temporary password:\n  {result.temporary_password}")
    typer.echo()
    typer.echo("Copy it now. It will not be shown again.")


def _create_targets(
    env_file: list[Path],
) -> list[tuple[str, Path | None]]:
    if not env_file:
        return [("current environment", None)]
    return [(str(p.resolve()), p) for p in env_file]


@app.command()
def create(
    username: str = typer.Argument(..., help="Redshift username to create"),
    env_file: Annotated[
        list[Path],
        typer.Option(
            "--env-file",
            exists=True,
            readable=True,
            help="Env file (KEY=value or export ...). Repeat to provision the same user on multiple clusters.",
        ),
    ] = [],
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Create a Redshift user with a temporary password, VALID UNTIL +6 months, and default group."""
    try:
        validate_username(username)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    targets = _create_targets(env_file)

    for label, path in targets:
        merged = merged_environ(path)
        try:
            config = load_config(merged)
        except EnvironmentError as exc:
            typer.echo(f"Configuration error ({label}): {exc}", err=True)
            raise typer.Exit(code=1)
        conn = None
        try:
            conn = get_connection(config)
            ensure_user_absent(conn, username)
        except UserAlreadyExistsError as exc:
            typer.echo(f"Error ({label}): {exc}", err=True)
            raise typer.Exit(code=1)
        except ValueError as exc:
            typer.echo(f"Error ({label}): {exc}", err=True)
            raise typer.Exit(code=1)
        except Exception as exc:
            typer.echo(f"Connection error ({label}): {exc}", err=True)
            raise typer.Exit(code=1)
        finally:
            if conn is not None:
                conn.close()

    typer.echo("Preflight OK — user is absent on all targets.")
    typer.echo()
    typer.echo("Targets:")
    for label, path in targets:
        merged = merged_environ(path)
        cfg = load_config(merged)
        typer.echo(f"  - {label}")
        typer.echo(f"      default group: {cfg.default_group}")
    planned_valid = compute_new_valid_until()
    typer.echo()
    typer.echo(f"  valid_until (after confirm): {_format_timestamp(planned_valid)}")
    typer.echo()
    typer.echo("This will:")
    typer.echo("  - CREATE USER with a generated password and VALID UNTIL +6 months")
    typer.echo("  - add the user to the default group on each target")
    typer.echo()

    if not yes:
        confirmed = typer.confirm("Continue?", default=False)
        if not confirmed:
            typer.echo("Aborted.")
            raise typer.Exit(code=0)

    password = generate_password()
    valid_until = compute_new_valid_until()

    for idx, (label, path) in enumerate(targets):
        merged = merged_environ(path)
        config = load_config(merged)
        try:
            conn = get_connection(config)
        except Exception as exc:
            typer.echo(f"Connection error ({label}): {exc}", err=True)
            _report_partial_create(idx, targets)
            raise typer.Exit(code=1)
        try:
            create_user_account(
                conn, username, config.default_group, password, valid_until
            )
        except UserAlreadyExistsError as exc:
            typer.echo(f"Error during create ({label}): {exc}", err=True)
            _report_partial_create(idx, targets)
            raise typer.Exit(code=1)
        except ValueError as exc:
            typer.echo(f"Error during create ({label}): {exc}", err=True)
            _report_partial_create(idx, targets)
            raise typer.Exit(code=1)
        except Exception as exc:
            typer.echo(f"Error during create ({label}): {exc}", err=True)
            _report_partial_create(idx, targets)
            raise typer.Exit(code=1)
        finally:
            conn.close()

    typer.echo()
    typer.echo(f"Temporary password:\n  {password}")
    typer.echo()
    typer.echo("Copy it now. It will not be shown again.")


def _report_partial_create(
    failed_index: int, targets: list[tuple[str, Path | None]]
) -> None:
    _report_partial_targets(
        failed_index,
        targets,
        "Earlier targets may already have this user created. "
        "Check Redshift and fix or drop the user before retrying.",
    )


def _report_partial_recover(
    failed_index: int, targets: list[tuple[str, Path | None]]
) -> None:
    _report_partial_targets(
        failed_index,
        targets,
        "Earlier targets may already have this user's password reset and VALID UNTIL updated. "
        "Check Redshift and align state before retrying.",
    )


def _report_partial_targets(
    failed_index: int,
    targets: list[tuple[str, Path | None]],
    earlier_message: str,
) -> None:
    if failed_index <= 0:
        return
    typer.echo(earlier_message, err=True)
    succeeded = [targets[i][0] for i in range(failed_index)]
    typer.echo(f"Succeeded before failure: {', '.join(succeeded)}", err=True)
