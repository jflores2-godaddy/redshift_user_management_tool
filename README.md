# redshift-user-admin

CLI tool for managing Redshift user accounts. Built for internal engineers who need to inspect user details, create new logins, and recover locked-out accounts.

## Features

- **info** -- Look up a Redshift user and display their username and password expiration date. Optional `--env-file` (repeatable) queries multiple clusters in one run.
- **recover** -- Reset a user's password and set `VALID UNTIL` to six calendar months from UTC now. Optional `--env-file` (repeatable) recovers the same login on multiple clusters with one password and one expiry after preflight.
- **create** -- Create a new user with a generated password, `VALID UNTIL` six calendar months ahead, and membership in the default group (see `REDSHIFT_DEFAULT_GROUP`). Supports multiple `--env-file` values so the same password and expiry are applied to more than one cluster after a single preflight across all targets.

## Prerequisites

- Python 3.11+
- Network access to your Redshift cluster

## Installation

```bash
git clone <repo-url>
cd redshift_user_management_tool
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Configuration

Set the following environment variables before running the tool:

| Variable                  | Required | Default | Description                        |
|---------------------------|----------|---------|------------------------------------|
| `REDSHIFT_HOST`           | Yes      | --      | Redshift cluster hostname          |
| `REDSHIFT_PORT`           | No       | `5439`  | Redshift cluster port              |
| `REDSHIFT_DATABASE`       | Yes      | --      | Database name                      |
| `REDSHIFT_ADMIN_USER`     | Yes      | --      | Admin username for authentication  |
| `REDSHIFT_ADMIN_PASSWORD` | Yes      | --      | Admin password for authentication  |
| `REDSHIFT_SSL`            | No       | `true`  | Enable SSL (`true`, `1`, or `yes`) |
| `REDSHIFT_DEFAULT_GROUP`  | No       | `analytics_general_readers` | Group passed to `ALTER GROUP ... ADD USER` after `CREATE USER` |

Example:

```bash
export REDSHIFT_HOST=my-cluster.abc123.us-east-1.redshift.amazonaws.com
export REDSHIFT_DATABASE=analytics
export REDSHIFT_ADMIN_USER=admin
export REDSHIFT_ADMIN_PASSWORD=secret
```

## Usage

### Inspect a user

```bash
redshift-user-admin info <username>
```

Example output (current shell environment only, no `--env-file`):

```
User found
  username:    userx
  valid_until: 2026-05-31 23:59:59
```

Query the same username on two clusters using env files (order matches the flags):

```bash
redshift-user-admin info userx --env-file bi.env --env-file sl.env
```

Example output when using multiple `--env-file` values:

```
[/path/to/bi.env]
  User found
    username:    userx
    valid_until: 2026-05-31 23:59:59

[/path/to/sl.env]
  User not found
```

If the user is missing on every target, the command exits with code 1 and prints an error after all sections.

### Recover a user account

Recovery always sets the new `VALID UNTIL` from **UTC now plus six calendar months**, not from the user’s previous expiry. That keeps multi-cluster runs aligned; accounts that already had a much later expiry will get a shorter window until the next extension.

```bash
redshift-user-admin recover <username>
```

Example output (current shell environment only, no `--env-file`):

```
User found
  username:            userx
  current valid_until: 2026-05-31 23:59:59
  new valid_until:     2026-11-30 23:59:59

This will:
  - reset password
  - set VALID UNTIL to 6 calendar months from now (UTC)

Continue? [y/N]: y

Temporary password:
  E$UJkz3OICj8BY

Copy it now. It will not be shown again.
```

Recover the same username on two clusters with one password and one `VALID UNTIL` (the user must exist on **every** target):

```bash
redshift-user-admin recover userx --env-file bi.env --env-file sl.env --yes
```

**Partial failures:** If recovery fails partway through a multi-target run, an earlier cluster may already have the new password and expiry while a later one does not. The CLI prints which targets had already succeeded; fix Redshift state before retrying.

Skip the confirmation prompt with `--yes`:

```bash
redshift-user-admin recover <username> --yes
```

### Create a user

The tool connects to each target, checks that the username is **not** already present (preflight), then asks for confirmation. After you confirm, it generates one password and one `VALID UNTIL` value and applies them to every target.

Single cluster using your current shell environment:

```bash
redshift-user-admin create <username>
```

Two clusters (for example BI and Serverless dev), same password on both, using env files whose variables override the process environment for that step only:

```bash
redshift-user-admin create <username> --env-file bi.env --env-file sl.env --yes
```

Omit `--yes` to get the interactive confirmation prompt.

**Partial failures:** If provisioning fails partway through a multi-target run, an earlier cluster may already contain the new user while a later one does not. The CLI prints which targets had already succeeded; fix Redshift state or retry as appropriate.

**Prerequisites:** The admin user must be allowed to `CREATE USER` and `ALTER GROUP` for `REDSHIFT_DEFAULT_GROUP`, and that group must exist on each cluster.

## Testing

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

## Security Notes

- Admin credentials are read from environment variables and never logged.
- Generated passwords are printed exactly once and never persisted or logged.
- The `recover` and `create` commands require interactive confirmation unless `--yes` is passed.
- Usernames are validated against a strict pattern (`^[A-Za-z][A-Za-z0-9_]{0,62}$`) and quoted as SQL identifiers to prevent injection.
- Passwords are escaped for SQL string literals (no single quotes, double quotes, or backslashes in generated passwords).
