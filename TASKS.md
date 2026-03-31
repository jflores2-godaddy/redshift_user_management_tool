# Tasks

Tracks implementation progress for `redshift-user-admin`. Refer to [PROJECT_SPEC.md](PROJECT_SPEC.md) for full requirements.

## Completed

- [x] **pyproject.toml** -- Build system (hatchling), dependencies, entry point, dev extras.
- [x] **redshift_user_admin/config.py** -- `RedshiftConfig` dataclass, `load_config()` from env vars.
- [x] **redshift_user_admin/models.py** -- `UserInfo` and `RecoveryResult` frozen dataclasses.
- [x] **redshift_user_admin/passwords.py** -- `generate_password()` using `secrets`, SQL-safe symbols.
- [x] **redshift_user_admin/db.py** -- `get_connection`, `fetch_user_info`, `reset_user_password`, `set_valid_until` with identifier quoting.
- [x] **redshift_user_admin/service.py** -- `validate_username`, `get_user_info`, `compute_new_valid_until`, `recover_user`.
- [x] **redshift_user_admin/cli.py** -- Typer app with `info` and `recover` commands, confirmation flow, formatted output.
- [x] **tests/** -- `test_validation.py`, `test_passwords.py`, `test_extension.py`, `test_service.py` (39 tests, all passing).
- [x] **Run tests** -- Installed in venv, `pytest` passes (39/39).
- [x] **README.md** -- Purpose, setup, env vars, install, usage examples, security notes.
