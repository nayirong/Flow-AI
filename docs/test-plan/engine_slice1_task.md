# Flow AI Python Engine — Slice 1 Implementation Task
## For @software-engineer

**Last Updated:** 16 April 2026
**Slice:** 1 (Foundation)
**Prerequisite:** None — builds from scratch
**Baseline:** main branch

---

## Goal

Implement the Foundation layer (Slice 1) of the Flow AI Python engine: configuration loading, client config with TTL caching, and Supabase client factories. All unit tests in `engine/tests/unit/` must pass.

---

## Context

Read these documents before starting:
- `docs/architecture/engine_build_spec.md` — full 5-slice build plan (you are implementing Slice 1)
- `docs/architecture/00_platform_architecture.md` — detailed component specs

The Flow AI engine is **client-agnostic**. All client-specific config is loaded at runtime by `client_id` from:
1. Shared Flow AI Supabase `clients` table (non-sensitive fields)
2. Railway env vars (high-sensitivity secrets like `meta_whatsapp_token`)

This slice creates the config foundation that all other slices depend on.

---

## Files to Create

Create these files with full implementations:

### 1. `engine/config/settings.py`

Pydantic settings model that loads Flow AI platform-level env vars.

**Required class:**
```python
from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    # Shared Flow AI Supabase (has clients table)
    shared_supabase_url: str
    shared_supabase_service_key: str
    
    # Anthropic API key for Claude
    anthropic_api_key: str
    
    # Logging
    log_level: str = "INFO"
    
    model_config = ConfigDict(env_file=".env", case_sensitive=False)

# Singleton instance
settings = Settings()
```

**Env var mapping:**
- `SHARED_SUPABASE_URL` → `shared_supabase_url`
- `SHARED_SUPABASE_SERVICE_KEY` → `shared_supabase_service_key`
- `ANTHROPIC_API_KEY` → `anthropic_api_key`
- `LOG_LEVEL` → `log_level` (optional, default "INFO")

**Error handling:**
- If any required field is missing, pydantic-settings will raise `ValidationError` automatically — no custom error handling needed

---

### 2. `engine/config/client_config.py`

ClientConfig model and `load_client_config()` function with in-process TTL cache.

**Required classes:**

```python
from dataclasses import dataclass
import os
import json
import time
from typing import Dict, Tuple

@dataclass
class ClientConfig:
    """Configuration for a single client, loaded from Supabase + env vars."""
    client_id: str
    display_name: str
    meta_phone_number_id: str       # from shared Supabase clients table
    meta_verify_token: str          # from shared Supabase clients table
    meta_whatsapp_token: str        # from env: {CLIENT_ID_UPPER}_META_WHATSAPP_TOKEN
    human_agent_number: str         # from shared Supabase clients table
    google_calendar_id: str | None  # from shared Supabase clients table
    google_calendar_creds: dict     # from env: {CLIENT_ID_UPPER}_GOOGLE_CALENDAR_CREDS (JSON string)
    supabase_url: str               # from env: {CLIENT_ID_UPPER}_SUPABASE_URL
    supabase_service_key: str       # from env: {CLIENT_ID_UPPER}_SUPABASE_SERVICE_KEY
    timezone: str                   # from shared Supabase clients table
    is_active: bool                 # from shared Supabase clients table

class ClientNotFoundError(Exception):
    """Raised when client_id not found or is_active=False."""
    pass

class ClientConfigError(Exception):
    """Raised when client config is invalid (e.g. missing env var)."""
    pass
```

**Required function:**

```python
# Cache structure: {client_id: (ClientConfig, expiry_timestamp)}
_cache: Dict[str, Tuple[ClientConfig, float]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes

async def load_client_config(client_id: str) -> ClientConfig:
    """
    Load client configuration from shared Supabase + env vars.
    
    Caches result for CACHE_TTL_SECONDS. Returns cached value if not expired.
    
    Raises:
        ClientNotFoundError: If client not found or is_active=False
        ClientConfigError: If required env var is missing
    """
    # 1. Check cache
    now = time.time()
    if client_id in _cache:
        config, expiry = _cache[client_id]
        if now < expiry:
            return config
    
    # 2. Query shared Supabase clients table
    from engine.integrations.supabase_client import get_shared_db
    
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
        timezone=row.get("timezone", "Asia/Singapore"),
        is_active=row["is_active"],
    )
    
    # 5. Cache with TTL
    _cache[client_id] = (config, now + CACHE_TTL_SECONDS)
    
    return config
```

**Test coverage required:**
- ✅ `load_client_config("hey-aircon")` returns ClientConfig with all fields
- ✅ `load_client_config("unknown-client")` raises `ClientNotFoundError`
- ✅ Second call within TTL returns cached value (Supabase called only once)
- ✅ Call after TTL expires re-queries Supabase
- ✅ Inactive client raises `ClientNotFoundError`

---

### 3. `engine/integrations/supabase_client.py`

Supabase AsyncClient factory functions.

**Required functions:**

```python
from supabase import create_async_client, AsyncClient
from engine.config.settings import settings
from engine.config.client_config import load_client_config

async def get_shared_db() -> AsyncClient:
    """
    Returns AsyncClient connected to Flow AI shared Supabase (has clients table).
    
    Uses SHARED_SUPABASE_URL and SHARED_SUPABASE_SERVICE_KEY from settings.
    
    Does NOT cache the client — creates a new one each call.
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
    """
    config = await load_client_config(client_id)
    
    return await create_async_client(
        supabase_url=config.supabase_url,
        supabase_key=config.supabase_service_key,
    )
```

**Note:** Do NOT cache the AsyncClient object. The `load_client_config()` already caches the config; creating a new AsyncClient each call is cheap and avoids connection issues.

**Test coverage required:**
- ✅ `get_shared_db()` returns an AsyncClient with `.table()` method
- ✅ `get_client_db("hey-aircon")` returns an AsyncClient
- ✅ `get_shared_db()` uses `settings.shared_supabase_url` and `settings.shared_supabase_service_key`
- ✅ `get_client_db()` calls `load_client_config(client_id)` and uses returned config

---

## Test Files (Already Created)

All test files are already written in `engine/tests/unit/`. Your implementation must make ALL these tests pass:

- `engine/tests/unit/test_settings.py`
- `engine/tests/unit/test_client_config.py`
- `engine/tests/unit/test_supabase_client.py`

Shared fixtures are in `engine/tests/conftest.py`.

---

## Package Dependencies

`engine/requirements.txt` is already created with all dependencies. Install them:

```bash
cd /Users/nayirong/Desktop/Personal/Professional\ Service/Flow\ AI
python3 -m pip install -r engine/requirements.txt
```

Key packages:
- `pydantic-settings>=2.2.0` — Settings model with env var loading
- `supabase>=2.4.0` — Supabase AsyncClient
- `pytest>=8.0.0`, `pytest-asyncio>=0.23.0` — testing

---

## Code Conventions (CRITICAL)

**All code must follow these rules:**

1. **Fully async**: Use `async def` for all functions. Use `await` for all I/O operations (Supabase calls).

2. **Functional patterns**: No classes except Pydantic models and `ClientConfig` dataclass. Functions should be pure where possible.

3. **No hardcoded client data**: Everything from env vars or Supabase. Zero references to "hey-aircon" or any specific client in implementation code (only in tests).

4. **Error handling on every external call**:
   ```python
   try:
       result = await external_call()
   except SomeError as e:
       # Log and raise a domain-specific error
       raise ClientConfigError(f"Failed to load config: {e}")
   ```

5. **No TODOs or placeholders**: All functions must be fully implemented. Tests must pass.

6. **Type hints**: Use type hints on all function signatures. Use `str | None` instead of `Optional[str]` (Python 3.10+ syntax).

7. **Docstrings**: Every function must have a docstring with Args, Returns, Raises sections.

---

## Validation Commands

After implementation, run these commands to verify success:

```bash
# Run all unit tests for Slice 1
cd /Users/nayirong/Desktop/Personal/Professional\ Service/Flow\ AI
python3 -m pytest engine/tests/unit/ -v

# Expected output: all tests pass, zero failures

# Verify imports work
python3 -c "from engine.config.settings import settings; print(settings)"
python3 -c "from engine.config.client_config import ClientConfig, load_client_config; print(ClientConfig)"
python3 -c "from engine.integrations.supabase_client import get_shared_db, get_client_db; print('OK')"
```

All commands must succeed with no import errors.

---

## Definition of Done

- [ ] All 3 implementation files created (`settings.py`, `client_config.py`, `supabase_client.py`)
- [ ] All unit tests pass: `pytest engine/tests/unit/ -v` shows 0 failures
- [ ] No import errors when importing from `engine.config.*` or `engine.integrations.*`
- [ ] No TODOs or placeholders in implementation files
- [ ] All functions have docstrings with type hints
- [ ] Code follows async/functional patterns (no blocking I/O, no unnecessary classes)

---

## Success Check

**Proof metric (founder-visible):** Can we load config for hey-aircon from a clean Python REPL?

```python
import asyncio
from engine.config.client_config import load_client_config

# Set required env vars first
import os
os.environ["SHARED_SUPABASE_URL"] = "https://shared.supabase.co"
os.environ["SHARED_SUPABASE_SERVICE_KEY"] = "key"
os.environ["ANTHROPIC_API_KEY"] = "key"
os.environ["HEY_AIRCON_META_WHATSAPP_TOKEN"] = "token"
os.environ["HEY_AIRCON_SUPABASE_URL"] = "url"
os.environ["HEY_AIRCON_SUPABASE_SERVICE_KEY"] = "key"

config = asyncio.run(load_client_config("hey-aircon"))
print(config)  # Should print ClientConfig with all fields
```

**Proxy metrics:**
- All unit tests green (proves implementation matches contract)
- Cache TTL test passes (proves caching works)
- ClientNotFoundError test passes (proves error handling works)

---

## Constraints

1. **No LangChain**: Use direct Anthropic SDK. This constraint applies in later slices, not Slice 1.
2. **No client-specific logic**: All code must work for any client_id via env vars + Supabase.
3. **No Redis**: In-process TTL cache using Python dict + `time.time()`.
4. **No Google Calendar yet**: Slice 1 only loads the creds; Slice 5 will use them.
5. **No FastAPI yet**: Slice 2 will add the webhook routes; Slice 1 is pure config/DB.

---

## Questions?

If any requirement is unclear, check:
1. `docs/architecture/engine_build_spec.md` — full slice breakdown
2. `docs/architecture/00_platform_architecture.md` § Component 1, 5, 6
3. Test files in `engine/tests/unit/` — they show exact expected behavior

If still unclear, ask @sdet-engineer before implementing.

---

## Format Command

Before committing, run the Python formatter:

```bash
python3 -m black engine/
```

This project uses `black` for consistent formatting. All files must be formatted before commit.
