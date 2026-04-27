"""
Client configuration model and loader with TTL caching.

Loads client-specific configuration from shared Supabase clients table
and environment variables.
"""
from dataclasses import dataclass
import os
import json
import time
from typing import Dict, Tuple

from engine.integrations.supabase_client import get_shared_db


@dataclass
class ClientConfig:
    """
    Configuration for a single client, loaded from Supabase + env vars.
    
    Attributes:
        client_id: Unique client identifier (e.g., "hey-aircon")
        display_name: Human-readable client name
        meta_phone_number_id: Meta WhatsApp phone number ID
        meta_verify_token: Meta webhook verification token
        meta_whatsapp_token: Meta WhatsApp API token (from env)
        human_agent_number: Phone number for escalation
        google_calendar_id: Google Calendar ID for bookings
        google_calendar_creds: Google Calendar service account credentials (from env)
        supabase_url: Client's Supabase project URL (from env)
        supabase_service_key: Client's Supabase service key (from env)
        timezone: Client's timezone
        is_active: Whether client is active
    """
    client_id: str
    display_name: str
    meta_phone_number_id: str
    meta_verify_token: str
    meta_whatsapp_token: str
    human_agent_number: str
    google_calendar_id: str | None
    google_calendar_creds: dict
    supabase_url: str
    supabase_service_key: str
    anthropic_api_key: str
    openai_api_key: str
    timezone: str
    is_active: bool
    sheets_sync_enabled: bool = False
    sheets_spreadsheet_id: str | None = None
    sheets_service_account_creds: dict | None = None


class ClientNotFoundError(Exception):
    """Raised when client_id not found or is_active=False."""
    pass


class ClientConfigError(Exception):
    """Raised when client config is invalid (e.g. missing env var)."""
    pass


# Cache structure: {client_id: (ClientConfig, expiry_timestamp)}
_cache: Dict[str, Tuple[ClientConfig, float]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


async def load_client_config(client_id: str) -> ClientConfig:
    """
    Load client configuration from shared Supabase + env vars.
    
    Caches result for CACHE_TTL_SECONDS. Returns cached value if not expired.
    
    Args:
        client_id: Client identifier (e.g., "hey-aircon")
        
    Returns:
        ClientConfig object with all fields populated
        
    Raises:
        ClientNotFoundError: If client not found or is_active=False
        ClientConfigError: If required env var is missing
    """
    # 1. Check cache
    now = time.time()
    if client_id in _cache:
        config, expiry = _cache[client_id]
        if now < expiry:
            # Defensive assertion: cache key must match stored client_id.
            # A mismatch indicates a cache corruption bug — fail loudly rather
            # than silently serving one client's config to another.
            assert config.client_id == client_id, (
                f"Cache key mismatch: expected '{client_id}', got '{config.client_id}'. "
                "Cache is corrupted — this is a bug, not a client error."
            )
            return config
    
    # 2. Query shared Supabase clients table
    db = await get_shared_db()
    response = await db.table("clients").select("*").eq("client_id", client_id).eq("is_active", True).limit(1).execute()
    
    if not response.data:
        raise ClientNotFoundError(f"Client '{client_id}' not found or inactive")
    
    row = response.data[0]
    
    # 3. Load secrets from env vars
    client_id_upper = client_id.upper().replace("-", "_")
    
    meta_whatsapp_token = os.getenv(f"{client_id_upper}_META_WHATSAPP_TOKEN")
    if not meta_whatsapp_token:
        raise ClientConfigError(f"Missing env var: {client_id_upper}_META_WHATSAPP_TOKEN")

    supabase_url = os.getenv(f"{client_id_upper}_SUPABASE_URL")
    if not supabase_url:
        raise ClientConfigError(f"Missing env var: {client_id_upper}_SUPABASE_URL")

    supabase_service_key = os.getenv(f"{client_id_upper}_SUPABASE_SERVICE_KEY")
    if not supabase_service_key:
        raise ClientConfigError(f"Missing env var: {client_id_upper}_SUPABASE_SERVICE_KEY")

    anthropic_api_key = os.getenv(f"{client_id_upper}_ANTHROPIC_API_KEY")
    if not anthropic_api_key:
        raise ClientConfigError(f"Missing env var: {client_id_upper}_ANTHROPIC_API_KEY")

    openai_api_key = os.getenv(f"{client_id_upper}_OPENAI_API_KEY")
    if not openai_api_key:
        raise ClientConfigError(f"Missing env var: {client_id_upper}_OPENAI_API_KEY")

    google_calendar_creds_json = os.getenv(f"{client_id_upper}_GOOGLE_CALENDAR_CREDS", "{}")
    google_calendar_creds = json.loads(google_calendar_creds_json)
    
    # 4. Construct ClientConfig
    config = ClientConfig(
        client_id=row["client_id"],
        display_name=row.get("display_name", ""),
        meta_phone_number_id=row["meta_phone_number_id"],
        meta_verify_token=row["meta_verify_token"],
        meta_whatsapp_token=meta_whatsapp_token,
        human_agent_number=row["human_agent_number"],
        google_calendar_id=row.get("google_calendar_id"),
        google_calendar_creds=google_calendar_creds,
        supabase_url=supabase_url,
        supabase_service_key=supabase_service_key,
        anthropic_api_key=anthropic_api_key,
        openai_api_key=openai_api_key,
        timezone=row.get("timezone", "Asia/Singapore"),
        is_active=row["is_active"],
        sheets_sync_enabled=row.get("sheets_sync_enabled", False),
        sheets_spreadsheet_id=row.get("sheets_spreadsheet_id"),
        sheets_service_account_creds=row.get("sheets_service_account_creds"),
    )
    
    # 5. Cache with TTL
    _cache[client_id] = (config, now + CACHE_TTL_SECONDS)
    
    return config
