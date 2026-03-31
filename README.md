# redshift-user-admin

CLI tool for managing Redshift user accounts. Built for internal engineers who need to inspect user details and recover locked-out accounts.

## Features

- **info** -- Look up a Redshift user and display their username and password expiration date.
- **recover** -- Reset a user's password and extend their `VALID UNTIL` by 6 calendar months.

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

Example output:

```
User found
  username:    userx
  valid_until: 2026-05-31 23:59:59
```

### Recover a user account

```bash
redshift-user-admin recover <username>
```

Example output:

```
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

Skip the confirmation prompt with `--yes`:

```bash
redshift-user-admin recover <username> --yes
```

## Testing

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

## Security Notes

- Admin credentials are read from environment variables and never logged.
- Generated passwords are printed exactly once and never persisted or logged.
- The `recover` command requires interactive confirmation unless `--yes` is passed.
- Usernames are validated against a strict pattern (`^[A-Za-z][A-Za-z0-9_]{0,62}$`) and quoted as SQL identifiers to prevent injection.
- Passwords are escaped for SQL string literals (no single quotes, double quotes, or backslashes in generated passwords).
