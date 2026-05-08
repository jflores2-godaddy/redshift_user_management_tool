# redshift-user-admin

CLI tool for managing Redshift user accounts. Built for internal engineers who need to inspect user details, create new logins, and recover locked-out accounts.

## Features

- **info** -- Look up a Redshift user and display their username and password expiration date. Optional `--env-file` (repeatable) queries multiple clusters in one run.
- **recover** -- Reset a user's password and set `VALID UNTIL` to six calendar months from UTC now. Optional `--env-file` (repeatable) recovers the same login on multiple clusters with one password and one expiry after preflight.
- **create** -- Create a new user with a generated password, `VALID UNTIL` six calendar months ahead, and membership in the default group (see `REDSHIFT_DEFAULT_GROUP`). Supports multiple `--env-file` values so the same password and expiry are applied to more than one cluster after a single preflight across all targets.
- **investigate** -- For a username and schema, print per-cluster checks: user row, group memberships, writer groups, sample table privileges (`HAS_TABLE_PRIVILEGE`), and schema owner. Use multiple `--env-file` values when you need to compare BI vs serverless before granting.
- **inspect-group** -- For a **group** name and schema, print **member count** (no username list), `SVV_SCHEMA_PRIVILEGES` and aggregate `SVV_RELATION_PRIVILEGES` for that group. Optional `--table` / `-t` lists `privilege_type` rows for one relation. **Exits with code 1** if the group does not exist (no further catalog queries). Use this to confirm a group has `USAGE` and relation-level grants. Visibility of `SVV_*` rows matches AWS docs (often superuser or unrestricted system-table access).
- **grant-access** -- Grant read (`ALTER GROUP` to `REDSHIFT_DEFAULT_GROUP`), write (inferred or `--writer-group`, plus `GRANT` on the schema), or both; SQL is printed before it runs. Re-runs the same checks afterward for verification. Supports `--dry-run` and `--yes`.

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

### Investigate access (DBA tickets)

Run against every cluster you care about first (for example BI, then serverless), using one `--env-file` per cluster in that order:

```bash
redshift-user-admin investigate <username> <schema> --env-file bi.env --env-file sl.env
```

Each target prints its own section (host, database) plus user existence, groups, `%writer%` groups on that cluster, sample `HAS_TABLE_PRIVILEGE` results, and schema owner. SQL is echoed to the terminal as it runs. If you are unsure which cluster needs a change, compare the two sections, then run `grant-access` with only the relevant `--env-file` argument(s).

### Inspect a group for a schema (validate grants)

Use when you need to verify that a **group** has explicit schema and relation privileges—for example `corporate_writers` on `ba_corporate`. If the group name is wrong, the command **fails immediately** after `pg_group` (exit code 1).

```bash
redshift-user-admin inspect-group corporate_writers ba_corporate --env-file bi.env
redshift-user-admin inspect-group corporate_writers ba_corporate --table bu_scorecards --env-file sl.env
```

Each target prints: group **member count** only, schema owner, `svv_schema_privileges` (`privilege_type` only), and **schema-wide** aggregates from `svv_relation_privileges` (distinct relation count and counts by `privilege_type`). By default, per-relation privilege lines are **omitted**; pass **`--table` / `-t`** with a relation name to print one row per `privilege_type` for that table. SQL is echoed before execution. The tool does **not** select `admin_option` from those SVV views: on some clusters that column resolves via `pg_user_has_admin_option`, which can return **42501 Insufficient privilege** for typical admin users.

**Catalog visibility:** Non-superuser admins may see incomplete `SVV_*` results per [Amazon Redshift visibility rules](https://docs.aws.amazon.com/redshift/latest/dg/cm_chap_system-tables.html#c_visibility-of-data-in-system-tables-and-views). Use a connection that can see all grants you need to validate.

| | `investigate <user> <schema>` | `inspect-group <group> <schema>` |
| --- | --- | --- |
| **Purpose** | User-centric access triage | Group-centric grant validation on a schema |
| **Identity** | Login must exist to inspect privileges | Group must exist or the command exits with code **1** |
| **Membership** | Lists the user’s Redshift groups | Prints **member count** only (no usernames) |
| **Relation / table detail** | `HAS_TABLE_PRIVILEGE` on a few sample tables | `SVV_RELATION_PRIVILEGES` aggregates for the schema; use **`--table` / `-t`** for one relation’s `privilege_type` rows |
| **Writer groups** | Lists `%writer%` groups and heuristic match | Not shown (you already pass the group name) |

### Grant access

Read-only grants add the user to `REDSHIFT_DEFAULT_GROUP` (default `analytics_general_readers`). Write grants pick a `*_writers` group from the cluster when the schema name matches (for example `ba_ecommerce` → `ecommerce_writers`); if nothing matches, pass `--writer-group` explicitly.

```bash
redshift-user-admin grant-access <username> <schema> --access read --env-file bi.env --yes
redshift-user-admin grant-access <username> <schema> --access both --env-file bi.env --env-file sl.env --dry-run
```

All `ALTER GROUP` / `GRANT` statements are printed before execution. With `--dry-run`, those statements are not executed (investigation `SELECT`s still run so the tool can resolve writer groups and show current state). Omit `--yes` for an interactive confirmation prompt.

**Partial failures:** If a multi-target grant fails partway through, an earlier cluster may already have grants applied. The CLI prints which targets had succeeded before the failure.

## Testing

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

## Security Notes

- Admin credentials are read from environment variables and never logged.
- Generated passwords are printed exactly once and never persisted or logged.
- The `recover`, `create`, and `grant-access` commands require interactive confirmation unless `--yes` is passed (`grant-access` also supports `--dry-run`).
- The `investigate`, `inspect-group`, and `grant-access` commands print SQL (including `SELECT`s) to the terminal before execution; admin passwords are still never logged.
- Usernames are validated against a strict pattern (`^[A-Za-z][A-Za-z0-9_]{0,62}$`) and quoted as SQL identifiers to prevent injection.
- Passwords are escaped for SQL string literals (no single quotes, double quotes, or backslashes in generated passwords).
