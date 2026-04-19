"""
Unit tests for engine/config/settings.py

Tests the Settings pydantic model loads environment variables correctly.
"""
import pytest
from pydantic import ValidationError


def test_settings_loads_from_env(mock_env_vars):
    """Test that Settings loads all required fields from environment variables."""
    from engine.config.settings import Settings

    settings = Settings()

    assert settings.shared_supabase_url == "https://shared.supabase.co"
    assert settings.shared_supabase_service_key == "shared_service_key_mock"
    assert settings.log_level == "INFO"


def test_settings_raises_on_missing_required_field(monkeypatch):
    """Test that Settings raises ValidationError if a required field is missing."""
    monkeypatch.setenv("SHARED_SUPABASE_URL", "https://shared.supabase.co")
    monkeypatch.delenv("SHARED_SUPABASE_SERVICE_KEY", raising=False)

    from engine.config.settings import Settings

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    assert "shared_supabase_service_key" in str(exc_info.value).lower()


def test_settings_log_level_default(monkeypatch):
    """Test that log_level defaults to INFO when not provided."""
    monkeypatch.setenv("SHARED_SUPABASE_URL", "https://shared.supabase.co")
    monkeypatch.setenv("SHARED_SUPABASE_SERVICE_KEY", "key")
    # LOG_LEVEL not set

    from engine.config.settings import Settings

    settings = Settings()
    assert settings.log_level == "INFO"
