# Project Spec: redshift-user-admin

## Goal

Build a Python CLI tool (`redshift-user-admin`) for internal engineer use to manage Redshift user accounts locally using admin credentials provided through environment variables.

## Main Use Case

Recover a Redshift user account by:

1. Receiving a username.
2. Checking if the user exists.
3. Showing basic user info (username, `VALID UNTIL`).
4. Automatically generating a secure temporary password, updating the user password, and extending the password expiration date by 6 months.
5. Showing the generated password once so the engineer can share it with the user.

Also support a command to only inspect user info.

## CLI Requirements

- Python 3.11+
- CLI framework: `typer`

### Command: `info`

```bash
redshift-user-admin info <username>
```

Behavior:

- Validate username.
- Connect to Redshift.
- Query the user.
- Print username and current `VALID UNTIL`.
- If user does not exist, print a clear error and exit non-zero.

### Command: `recover`

```bash
redshift-user-admin recover <username>
redshift-user-admin recover <username> --yes
```

Behavior:

- Validate username.
- Connect to Redshift.
- Query the user.
- Display username, current `VALID UNTIL`, and new computed `VALID UNTIL`.
- Ask for confirmation before making changes (skip with `--yes`).
- Generate a secure temporary password.
- Execute password reset and `ALTER USER <username> VALID UNTIL '<timestamp>'`.
- Print the generated password once.
- Do not log or persist the password.

## Extension Logic

Implement "extend by 6 months" as:

- `base_date = max(current_valid_until, now)` if `current_valid_until` exists, otherwise `base_date = now`.
- `new_valid_until = base_date + 6 months`.
- Use calendar-aware month arithmetic via `dateutil.relativedelta`, not `timedelta(days=180)`.

## Redshift Connection

Environment variables:

| Variable                | Required | Default |
|-------------------------|----------|---------|
| `REDSHIFT_HOST`         | Yes      | --      |
| `REDSHIFT_PORT`         | No       | `5439`  |
| `REDSHIFT_DATABASE`     | Yes      | --      |
| `REDSHIFT_ADMIN_USER`   | Yes      | --      |
| `REDSHIFT_ADMIN_PASSWORD` | Yes    | --      |
| `REDSHIFT_SSL`          | No       | `true`  |

Use `redshift_connector` to connect.

## SQL Behavior

- Fetch user info from `pg_user` (`usename`, `valuntil`).
- DDL: `ALTER USER` to change password and set `VALID UNTIL`.
- Validate usernames strictly before using them in SQL.
- Quote identifiers with `"` to prevent injection.
- Escape password string literals (double single quotes).

## Username Validation

Strict regex:

```
^[A-Za-z][A-Za-z0-9_]{0,62}$
```

If invalid, fail with a clear message.

## Password Generation

- Use `secrets`, not `random`.
- Length: 16 (configurable, minimum 4).
- At least one uppercase, one lowercase, one digit, one symbol.
- Symbols must be SQL-safe: exclude single quote, double quote, and backslash.
- Never persist or log generated passwords.

## Security Requirements

- Never log admin password.
- Never log generated user passwords.
- Only print generated password once after success.
- Require confirmation unless `--yes`.
- Fail safely and clearly.
- Handle connection errors gracefully.

## Project Structure

```
redshift_user_admin/
  __init__.py
  cli.py          # Typer app, info and recover commands, confirmation flow
  config.py       # Load and validate environment variables
  db.py           # Redshift connection factory and SQL operations
  service.py      # Business logic: get user info, compute dates, recover user
  passwords.py    # Secure password generation
  models.py       # Dataclasses for UserInfo and RecoveryResult
tests/
  __init__.py
  test_validation.py
  test_passwords.py
  test_extension.py
  test_service.py
pyproject.toml
README.md
PROJECT_SPEC.md
TASKS.md
```

## Dependencies

### Runtime

- `typer[all]`
- `redshift-connector`
- `python-dateutil`

### Dev

- `pytest`
- `pytest-mock`

## Output Format

```bash
$ redshift-user-admin info userx
User found
  username:    userx
  valid_until: 2026-05-31 23:59:59
```

```bash
$ redshift-user-admin recover userx
User found
  username:          userx
  current valid_until: 2026-05-31 23:59:59
  new valid_until:     2026-11-30 23:59:59

This will:
  - reset password
  - extend validity by 6 months

Continue? [y/N]: y

Temporary password:
  E$UJkz3OICj8BY

Copy it now. It will not be shown again.
```

## Testing

- Username validation: valid and invalid inputs, SQL injection attempts.
- Password generation: correct length, character class requirements, forbidden characters, uniqueness.
- Valid-until extension: future date, past date, None, calendar-month edge cases.
- Service behavior: mocked DB calls for get_user_info and recover_user.

## README

Must include: purpose, setup, environment variables, install instructions, usage examples for `info` and `recover`, and security notes.
