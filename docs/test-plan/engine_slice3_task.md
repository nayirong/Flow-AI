# Engine Slice 3 — Message Handler + Escalation Gate
## Task Brief for @software-engineer

**Worktree:** `.worktree/engine-slice3-msghandler`
**Branch:** `engine/slice3-msghandler`
**Baseline:** `engine/slice2-webhook` (commit d760df1)
**Prerequisite:** Slice 2 (Webhook) — already on this branch
**Architecture ref:** `docs/architecture/00_platform_architecture.md` — Component 2 (Escalation Gate), Component 7 (Message Logging)
**Build spec ref:** `docs/architecture/engine_build_spec.md` — Slice 3 section

---

## Goal

Implement the inbound message handler with escalation gate and Meta send_message. Replace the `handle_inbound_message` stub in `engine/api/webhook.py` with a real import from `engine.core.message_handler`.

---

## Proof Metric

`interactions_log` receives an inbound row AND the escalation gate correctly routes: escalated customer → holding reply (no agent), non-escalated customer → "Escalation gate passed" log, new customer → `customers` INSERT.

---

## Files to Create / Modify

### Create: `engine/core/__init__.py`
Empty file — package marker only.

### Create: `engine/core/message_handler.py`

Full implementation of `handle_inbound_message()`:

```python
"""
Inbound message orchestration for Flow AI engine.

Flow:
    1. Load client config
    2. Get client DB connection
    3. Log inbound message to interactions_log (always first, before any gate)
    4. Check escalation gate (hard programmatic check — never agent-decided)
       - escalation_flag = TRUE: send holding reply, log outbound, return
    5. Upsert customer row (new → INSERT, returning → UPDATE last_seen)
    6. Log "Escalation gate passed for {phone_number}" — Slice 4 will add agent call here

All exceptions MUST be caught. Never propagate — this runs as a BackgroundTask.
On unrecoverable error: attempt fallback reply to customer, log error.
"""
import logging

logger = logging.getLogger(__name__)

HOLDING_REPLY = (
    "Our team is currently looking into your request. "
    "A member of our team will be in touch with you shortly."
)
FALLBACK_REPLY = (
    "Sorry, we encountered a technical issue. Please try again shortly."
)


async def handle_inbound_message(
    client_id: str,
    phone_number: str,
    message_text: str,
    message_type: str = "text",
    message_id: str = "",
    display_name: str = "",
) -> None:
    """
    Main inbound message orchestration. Called as a BackgroundTask from webhook.

    Never raises. All exceptions are caught and logged internally.
    """
    ...
```

**Implementation requirements:**

1. Import `load_client_config`, `ClientNotFoundError` from `engine.config.client_config`
2. Import `get_client_db` from `engine.integrations.supabase_client`
3. Import `send_message` from `engine.integrations.meta_whatsapp`
4. Step 1: `client_config = await load_client_config(client_id)` — wrap in try/except `ClientNotFoundError`; on error log and return
5. Step 2: `db = get_client_db(client_id)` — this is synchronous (returns supabase client)
6. Step 3: Insert to `interactions_log`:
   ```python
   await db.table("interactions_log").insert({
       "phone_number": phone_number,
       "direction": "inbound",
       "message_text": message_text,
       "message_type": message_type,
   }).execute()
   ```
   Wrap in try/except — log failure but continue
7. Step 4: Query escalation flag:
   ```python
   result = await db.table("customers").select("escalation_flag, escalation_reason").eq("phone_number", phone_number).limit(1).execute()
   ```
   - If `result.data` and `result.data[0]["escalation_flag"] is True`:
     - Call `await send_message(client_config.meta_phone_number_id, client_config.meta_whatsapp_token, phone_number, HOLDING_REPLY)`
     - Log outbound to `interactions_log` (direction='outbound', message_text=HOLDING_REPLY)
     - Return
8. Step 5: Upsert customer:
   - If `result.data` is empty (new customer):
     ```python
     await db.table("customers").insert({
         "phone_number": phone_number,
         "customer_name": display_name,
         "escalation_flag": False,
         "total_bookings": 0,
     }).execute()
     ```
   - If `result.data` exists and not escalated:
     ```python
     await db.table("customers").update({"last_seen": "NOW()"}).eq("phone_number", phone_number).execute()
     ```
9. Step 6: Log "Escalation gate passed for {phone_number}"
10. Outer try/except around the whole function body: on any uncaught exception, attempt `send_message(FALLBACK_REPLY)`, log the exception, return

### Modify: `engine/integrations/meta_whatsapp.py`

Add `send_message()` to the existing file (keep `verify_webhook_token()` unchanged):

```python
async def send_message(
    phone_number_id: str,
    whatsapp_token: str,
    to: str,
    message: str,
) -> bool:
    """
    Send a WhatsApp text message via Meta Cloud API.

    POST https://graph.facebook.com/v19.0/{phone_number_id}/messages
    Authorization: Bearer {whatsapp_token}
    Content-Type: application/json

    Returns True on success (HTTP 2xx), False on any failure. Never raises.
    """
    import httpx

    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {whatsapp_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=10.0)
        if response.is_success:
            return True
        logger.warning("Meta send_message non-2xx: %s %s", response.status_code, response.text[:200])
        return False
    except Exception as exc:
        logger.error("Meta send_message exception: %s", exc)
        return False
```

### Modify: `engine/api/webhook.py`

Replace the stub `handle_inbound_message` local function with an import. Change:

```python
# Old stub (remove this entire function):
async def handle_inbound_message(
    client_id: str,
    phone_number: str,
    message_text: str,
) -> None:
    ...stub body...
```

Replace with:

```python
from engine.core.message_handler import handle_inbound_message
```

Update the `background_tasks.add_task()` call to pass all 6 fields:

```python
background_tasks.add_task(
    handle_inbound_message,
    client_id,
    phone_number,
    message_text,
    message_type,
    message_id,
    display_name,
)
```

---

## Tests to Write

### `engine/tests/unit/test_message_handler.py`

All tests use `unittest.mock.AsyncMock` / `patch`. No real network calls. No real Supabase.

The mock pattern for Supabase chained calls (`.table().insert().execute()`) uses `MagicMock` with chained returns. See `engine/tests/conftest.py` for existing fixtures.

```python
"""
Slice 3 — Message Handler unit tests

Mocks:
- engine.core.message_handler.load_client_config  → AsyncMock returning mock ClientConfig
- engine.core.message_handler.get_client_db       → returns mock_db (MagicMock with chained methods)
- engine.core.message_handler.send_message        → AsyncMock returning True/False
"""
```

**Required test cases:**

1. `test_inbound_logged_before_processing`
   - Mock db returns no escalation row (new customer)
   - Call `handle_inbound_message`
   - Assert `db.table("interactions_log").insert(...)` was called with `direction="inbound"` before escalation query

2. `test_escalated_customer_gets_holding_reply`
   - Mock db escalation query returns `[{"escalation_flag": True, "escalation_reason": "angry customer"}]`
   - Assert `send_message` called with `HOLDING_REPLY`
   - Assert no "Escalation gate passed" log

3. `test_escalated_customer_outbound_logged`
   - Same as above — assert second `interactions_log` INSERT called with `direction="outbound"` and `message_text=HOLDING_REPLY`

4. `test_new_customer_row_created`
   - Mock db escalation returns empty list `[]`
   - Assert `db.table("customers").insert(...)` called (not update)

5. `test_returning_customer_last_seen_updated`
   - Mock db escalation returns `[{"escalation_flag": False, "escalation_reason": None}]`
   - Assert `db.table("customers").update({"last_seen": "NOW()"}).eq(...)` called

6. `test_inactive_client_handled_gracefully`
   - Mock `load_client_config` raises `ClientNotFoundError`
   - Assert no exception propagates (function returns normally)
   - Assert `send_message` NOT called

7. `test_supabase_failure_handled_gracefully`
   - Mock `db.table(...).insert(...).execute()` raises `Exception("DB down")`
   - Assert no exception propagates from `handle_inbound_message`

8. `test_meta_send_failure_handled_gracefully`
   - Escalated customer path, `send_message` returns `False`
   - Assert no exception propagates

9. `test_non_escalated_customer_proceeds`
   - Mock escalation returns `[{"escalation_flag": False, "escalation_reason": None}]`
   - Assert `send_message` NOT called with HOLDING_REPLY
   - Assert "Escalation gate passed" appears in logs (use `caplog`)

10. `test_send_message_posts_correct_payload` (tests `send_message` via message_handler)
    - Escalated customer path
    - Assert `send_message` called with correct `phone_number_id`, `token`, `to`, `HOLDING_REPLY`

### `engine/tests/unit/test_meta_whatsapp.py`

Use `respx` to mock httpx. Import from `engine.integrations.meta_whatsapp`.

1. `test_send_message_success`
   - Mock POST to `https://graph.facebook.com/v19.0/test_phone_id/messages` returns 200
   - Assert `send_message(...)` returns `True`
   - Assert request has correct `Authorization: Bearer` header and JSON body shape

2. `test_send_message_http_error`
   - Mock POST returns 400
   - Assert `send_message(...)` returns `False`
   - Assert no exception propagates

3. `test_send_message_network_error`
   - Mock `httpx.AsyncClient.post` raises `httpx.ConnectError`
   - Assert `send_message(...)` returns `False`

---

## Code Conventions

- All async throughout (`async def`, `await`)
- Use `httpx.AsyncClient` for Meta API calls
- Use Python `logging` — `logger = logging.getLogger(__name__)`
- Never hardcode client data — use `client_config.*` fields
- Escalation gate is a hard programmatic check — not configurable, not agent-decided
- `HOLDING_REPLY` constant defined at module level in `message_handler.py`

---

## Validate Commands

Run from inside the worktree:

```bash
cd "/Users/nayirong/Desktop/Personal/Professional Service/Flow AI/.worktree/engine-slice3-msghandler"

# All unit tests — Slice 1 + 2 + 3 must all pass
python3 -m pytest engine/tests/unit/ -v

# Slice 3 tests only (during development)
python3 -m pytest engine/tests/unit/test_message_handler.py engine/tests/unit/test_meta_whatsapp.py -v
```

**All tests must pass before marking complete.**

---

## Format Command

No formatter is configured for this project (no black/ruff config present). Ensure code follows PEP 8 conventions manually — consistent indentation, no trailing whitespace, consistent import ordering (stdlib → third-party → local).

---

## Boundary Verification

**Architecture contract ref:** `docs/architecture/00_platform_architecture.md` — Appendix A: Meta Webhook Payload Reference — "Meta send message request"

**Exact interface from contract:**
```
POST https://graph.facebook.com/v19.0/{META_PHONE_NUMBER_ID}/messages
Authorization: Bearer {META_WHATSAPP_TOKEN}
Content-Type: application/json

{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "<phone_number>",
  "type": "text",
  "text": { "body": "<message_text>" }
}
```

The `send_message()` implementation MUST match this exact shape. Do not deviate. Pass `json=payload` to `httpx` (not `content=json.dumps(payload)`) — this handles special characters automatically as noted in the contract.
