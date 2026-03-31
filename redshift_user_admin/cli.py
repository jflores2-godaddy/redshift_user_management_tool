from __future__ import annotations

import typer

from redshift_user_admin.config import load_config
from redshift_user_admin.db import get_connection
from redshift_user_admin.service import (
    UserNotFoundError,
    compute_new_valid_until,
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
def info(username: str = typer.Argument(..., help="Redshift username to look up")) -> None:
    """Show basic info for a Redshift user."""
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
        raise typer.Exit(code=1)
    finally:
        conn.close()

    typer.echo("User found")
    typer.echo(f"  username:    {user.username}")
    typer.echo(f"  valid_until: {_format_timestamp(user.valid_until)}")


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
