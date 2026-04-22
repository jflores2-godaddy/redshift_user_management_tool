from redshift_user_admin.config import load_config


def test_load_config_default_group_from_env() -> None:
    env = {
        "REDSHIFT_HOST": "h.example.com",
        "REDSHIFT_DATABASE": "db",
        "REDSHIFT_ADMIN_USER": "admin",
        "REDSHIFT_ADMIN_PASSWORD": "pw",
        "REDSHIFT_DEFAULT_GROUP": "my_readers",
    }
    cfg = load_config(env)
    assert cfg.default_group == "my_readers"


def test_load_config_default_group_when_unset() -> None:
    env = {
        "REDSHIFT_HOST": "h.example.com",
        "REDSHIFT_DATABASE": "db",
        "REDSHIFT_ADMIN_USER": "admin",
        "REDSHIFT_ADMIN_PASSWORD": "pw",
    }
    cfg = load_config(env)
    assert cfg.default_group == "analytics_general_readers"
