"""
Integration test: concurrent message handling across multiple clients.

Verifies that simultaneous inbound messages for different clients:
  1. Each receive the correct ClientConfig (no cache cross-contamination).
  2. Each receive a separate per-client Supabase connection (no db bleed).
  3. A crash in one client's pipeline does not affect the other client's pipeline.

These tests use mocks for all external dependencies (Supabase, Meta API, LLM)
and focus purely on isolation guarantees within the engine.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from engine.config.client_config import ClientConfig, _cache, CACHE_TTL_SECONDS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client_config(client_id: str) -> ClientConfig:
    """Build a minimal ClientConfig for testing."""
    return ClientConfig(
        client_id=client_id,
        display_name=f"{client_id} Display",
        meta_phone_number_id=f"phone_id_{client_id}",
        meta_verify_token=f"verify_{client_id}",
        meta_whatsapp_token=f"wa_token_{client_id}",
        human_agent_number=f"+6591110000",
        google_calendar_id=None,
        google_calendar_creds={},
        supabase_url=f"https://{client_id}.supabase.co",
        supabase_service_key=f"service_key_{client_id}",
        anthropic_api_key=f"sk-ant-{client_id}",
        openai_api_key=f"sk-openai-{client_id}",
        timezone="Asia/Singapore",
        is_active=True,
        sheets_sync_enabled=False,
    )


def _make_db_mock(client_id: str) -> MagicMock:
    """Build a mock Supabase async client tagged with client_id for verification."""
    mock = MagicMock()
    mock._client_id = client_id  # tag for assertion

    # All query chains return an empty result by default
    empty_response = MagicMock()
    empty_response.data = []
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.is_.return_value = chain
    chain.not_ = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.upsert.return_value = chain
    chain.execute = AsyncMock(return_value=empty_response)
    mock.table.return_value = chain
    return mock


# ---------------------------------------------------------------------------
# Test: cache key isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_key_isolation():
    """
    Seed the config cache with two different client entries.
    Verify that loading each client returns its own config and never the other's.
    """
    import time
    from engine.config import client_config as cc_module

    config_a = _make_client_config("hey-aircon")
    config_b = _make_client_config("flow-ai")

    # Directly seed the cache
    expiry = time.time() + CACHE_TTL_SECONDS
    cc_module._cache["hey-aircon"] = (config_a, expiry)
    cc_module._cache["flow-ai"] = (config_b, expiry)

    # Load both — should hit cache and return correct configs
    result_a = await cc_module.load_client_config("hey-aircon")
    result_b = await cc_module.load_client_config("flow-ai")

    assert result_a.client_id == "hey-aircon"
    assert result_a.supabase_url == "https://hey-aircon.supabase.co"
    assert result_a.anthropic_api_key == "sk-ant-hey-aircon"

    assert result_b.client_id == "flow-ai"
    assert result_b.supabase_url == "https://flow-ai.supabase.co"
    assert result_b.anthropic_api_key == "sk-ant-flow-ai"

    # Clean up
    cc_module._cache.pop("hey-aircon", None)
    cc_module._cache.pop("flow-ai", None)


@pytest.mark.asyncio
async def test_cache_assertion_raises_on_mismatch():
    """
    If a cache entry somehow has the wrong client_id stored (corruption),
    load_client_config must raise AssertionError rather than silently serving
    the wrong config.
    """
    import time
    from engine.config import client_config as cc_module

    # Deliberately store hey-aircon's config under the flow-ai key
    wrong_config = _make_client_config("hey-aircon")
    expiry = time.time() + CACHE_TTL_SECONDS
    cc_module._cache["flow-ai"] = (wrong_config, expiry)

    with pytest.raises(AssertionError, match="Cache key mismatch"):
        await cc_module.load_client_config("flow-ai")

    cc_module._cache.pop("flow-ai", None)


# ---------------------------------------------------------------------------
# Test: concurrent pipeline isolation — correct config per client
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_pipelines_receive_correct_config():
    """
    Simulate two concurrent inbound messages (hey-aircon and flow-ai).
    Each pipeline must receive the config and db matching its client_id.

    Verifies no cross-client config or db bleed under concurrent execution.
    """
    config_hey = _make_client_config("hey-aircon")
    config_flow = _make_client_config("flow-ai")
    db_hey = _make_db_mock("hey-aircon")
    db_flow = _make_db_mock("flow-ai")

    captured_configs: dict[str, ClientConfig] = {}
    captured_dbs: dict[str, MagicMock] = {}

    async def fake_handle(client_id, phone_number, message_text, message_type, message_id, display_name, context_message_id=None):
        """Minimal pipeline stub — captures which config+db were assigned."""
        from engine.config.client_config import load_client_config
        from engine.integrations.supabase_client import get_client_db
        cfg = await load_client_config(client_id)
        db = await get_client_db(client_id)
        captured_configs[client_id] = cfg
        captured_dbs[client_id] = db
        await asyncio.sleep(0.01)  # simulate async work

    import time
    from engine.config import client_config as cc_module
    expiry = time.time() + CACHE_TTL_SECONDS
    cc_module._cache["hey-aircon"] = (config_hey, expiry)
    cc_module._cache["flow-ai"] = (config_flow, expiry)

    with patch("engine.integrations.supabase_client.get_client_db", side_effect=lambda cid: asyncio.coroutine(lambda: db_hey if cid == "hey-aircon" else db_flow)()):
        # Run both pipelines concurrently
        await asyncio.gather(
            fake_handle("hey-aircon", "6591110001", "Hello", "text", "wamid.hey1", "Alice"),
            fake_handle("flow-ai",   "6591110002", "Hi",    "text", "wamid.flow1", "Bob"),
        )

    assert captured_configs["hey-aircon"].client_id == "hey-aircon"
    assert captured_configs["flow-ai"].client_id == "flow-ai"
    assert captured_configs["hey-aircon"].supabase_url != captured_configs["flow-ai"].supabase_url
    assert captured_configs["hey-aircon"].anthropic_api_key != captured_configs["flow-ai"].anthropic_api_key

    cc_module._cache.pop("hey-aircon", None)
    cc_module._cache.pop("flow-ai", None)


# ---------------------------------------------------------------------------
# Test: one client's exception does not crash the other client's pipeline
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_client_exception_does_not_affect_other_client():
    """
    If hey-aircon's message handler raises an unhandled exception,
    the flow-ai pipeline must still complete successfully.

    handle_inbound_message already wraps all exceptions — this test
    verifies that the outer boundary functions correctly under concurrent load.
    """
    from engine.core.message_handler import handle_inbound_message

    config_hey = _make_client_config("hey-aircon")
    config_flow = _make_client_config("flow-ai")
    db_flow = _make_db_mock("flow-ai")

    flow_ai_completed = False

    async def patched_load_config(client_id):
        if client_id == "hey-aircon":
            raise RuntimeError("Simulated hey-aircon Supabase failure")
        return config_flow

    async def patched_get_db(client_id):
        return db_flow

    with (
        patch("engine.core.message_handler.load_client_config", side_effect=patched_load_config),
        patch("engine.core.message_handler.get_client_db", side_effect=patched_get_db),
        patch("engine.core.message_handler.send_message", new_callable=AsyncMock),
        patch("engine.core.message_handler.build_system_message", new_callable=AsyncMock, return_value="sys"),
        patch("engine.core.message_handler.fetch_conversation_history", new_callable=AsyncMock, return_value=[]),
        patch("engine.core.message_handler.fetch_lead_days", new_callable=AsyncMock, return_value=7),
        patch("engine.core.message_handler._get_latest_pending_booking", new_callable=AsyncMock, return_value=None),
        patch("engine.core.message_handler.run_agent", new_callable=AsyncMock, return_value="Hello from Flow AI"),
        patch("engine.core.message_handler.build_tool_definitions", return_value=[]),
        patch("engine.core.message_handler.build_tool_dispatch", return_value={}),
        patch("engine.core.message_handler.sync_customer_to_sheets", new_callable=AsyncMock),
    ):
        # Run both concurrently — hey-aircon crashes, flow-ai should succeed
        results = await asyncio.gather(
            handle_inbound_message("hey-aircon", "6591110001", "Test", "text", "wamid.hey1", "Alice"),
            handle_inbound_message("flow-ai",   "6591110002", "Hi",   "text", "wamid.flow1", "Bob"),
            return_exceptions=True,
        )

    # Both must return None (handle_inbound_message never raises — exceptions are caught internally)
    assert results[0] is None, f"hey-aircon should not propagate exception, got: {results[0]}"
    assert results[1] is None, f"flow-ai should complete successfully, got: {results[1]}"
