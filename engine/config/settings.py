"""
Settings model for Flow AI engine.

Loads platform-level environment variables using pydantic-settings.
"""
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    """
    Flow AI platform-level settings loaded from environment variables.
    
    Required env vars:
        - SHARED_SUPABASE_URL: URL to Flow AI shared Supabase (contains clients table)
        - SHARED_SUPABASE_SERVICE_KEY: Service key for shared Supabase
        - ANTHROPIC_API_KEY: API key for Claude
        - LOG_LEVEL: Logging level (optional, defaults to INFO)
    """
    # Shared Flow AI Supabase (has clients table)
    shared_supabase_url: str
    shared_supabase_service_key: str

    # Internal Telegram alerting (optional — alerts silently disabled if unset)
    telegram_bot_token: str | None = None
    telegram_alert_chat_id: str | None = None

    # Logging
    log_level: str = "INFO"
    
    model_config = ConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


# Lazy singleton — only instantiated on first access so tests can set env vars first.
_settings_instance: "Settings | None" = None


def get_settings() -> "Settings":
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance


# Convenience proxy — behaves like the singleton but is lazily created.
class _SettingsProxy:
    def __getattr__(self, name: str):
        return getattr(get_settings(), name)


settings = _SettingsProxy()
