from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from redshift_user_admin.config import load_config
from redshift_user_admin.db import get_connection
from redshift_user_admin.env_file import merged_environ
from redshift_user_admin.passwords import generate_password
from redshift_user_admin.service import (
    UserAlreadyExistsError,
    UserNotFoundError,
    compute_new_valid_until,
    create_user_account,
    ensure_user_absent,
    get_user_info,
    recover_user,
    validate_username,
)

app = typer.Typer(help="Redshift user account management tool.")


def _format_timestamp(dt) -> str:
    if dt is None:
        return "not set"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


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
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Recover a Redshift user account: reset password and extend validity."""
    try:
        validate_username(username)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

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

    new_valid_until = compute_new_valid_until(user.valid_until)

    typer.echo("User found")
    typer.echo(f"  username:          {user.username}")
    typer.echo(f"  current valid_until: {_format_timestamp(user.valid_until)}")
    typer.echo(f"  new valid_until:     {_format_timestamp(new_valid_until)}")
    typer.echo()
    typer.echo("This will:")
    typer.echo("  - reset password")
    typer.echo("  - extend validity by 6 months")
    typer.echo()

    if not yes:
        confirmed = typer.confirm("Continue?", default=False)
        if not confirmed:
            typer.echo("Aborted.")
            conn.close()
            raise typer.Exit(code=0)

    try:
        result = recover_user(conn, username)
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
    planned_valid = compute_new_valid_until(None)
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
    valid_until = compute_new_valid_until(None)

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
    if failed_index <= 0:
        return
    typer.echo(
        "Earlier targets may already have this user created. "
        "Check Redshift and fix or drop the user before retrying.",
        err=True,
    )
    succeeded = [targets[i][0] for i in range(failed_index)]
    typer.echo(f"Succeeded before failure: {', '.join(succeeded)}", err=True)
