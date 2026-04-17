"""
Supabase AsyncClient factory functions.

Creates Supabase clients for shared Flow AI database and client-specific databases.
"""
from supabase import create_async_client, AsyncClient
from engine.config.settings import settings


async def get_shared_db() -> AsyncClient:
    """
    Returns AsyncClient connected to Flow AI shared Supabase (has clients table).
    
    Uses SHARED_SUPABASE_URL and SHARED_SUPABASE_SERVICE_KEY from settings.
    
    Does NOT cache the client — creates a new one each call.
    
    Returns:
        AsyncClient connected to shared Supabase
    """
    return await create_async_client(
        supabase_url=settings.shared_supabase_url,
        supabase_key=settings.shared_supabase_service_key,
    )


async def get_client_db(client_id: str) -> AsyncClient:
    """
    Returns AsyncClient connected to the client's own Supabase project.
    
    Uses ClientConfig to get supabase_url and supabase_service_key for this client_id.
    
    Does NOT cache the client — creates a new one each call.
    
    Args:
        client_id: Client identifier (e.g., "hey-aircon")
        
    Returns:
        AsyncClient connected to client's Supabase project
        
    Raises:
        ClientNotFoundError: If client not found or is_active=False
        ClientConfigError: If required env var is missing
    """
    # Import here to avoid circular dependency
    from engine.config.client_config import load_client_config
    
    config = await load_client_config(client_id)
    
    return await create_async_client(
        supabase_url=config.supabase_url,
        supabase_key=config.supabase_service_key,
    )
