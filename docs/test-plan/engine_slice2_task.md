# Slice 2 — Webhook Implementation Task
## For @software-engineer

**Status:** Ready for implementation
**Created:** 17 April 2026
**Prerequisites:** Slice 1 complete (all 12 tests passing)

---

## Goal

Build the FastAPI webhook receiver for the Flow AI Python engine. This component receives inbound WhatsApp messages from Meta Cloud API, performs webhook verification, and spawns background tasks to process messages.

**Definition of Done:** All 22 tests pass (12 Slice 1 + 10 Slice 2).

---

## Files to Create

### 1. `engine/api/__init__.py`
Empty file — makes `api` a package.

### 2. `engine/api/webhook.py`
FastAPI application with 3 routes:
- `GET /health` — Railway health check
- `GET /webhook/whatsapp/{client_id}` — Meta webhook verification
- `POST /webhook/whatsapp/{client_id}` — Receive inbound WhatsApp messages

### 3. `engine/integrations/meta_whatsapp.py`
Meta Cloud API integration functions. For Slice 2, only `verify_webhook_token()` is needed.
`send_message()` will be added in Slice 3.

---

## Detailed Specifications

### `engine/api/webhook.py`

#### Imports

```python
from fastapi import FastAPI, Request, BackgroundTasks, Query, Response
from fastapi.responses import PlainTextResponse
import logging

from engine.config.client_config import load_client_config, ClientNotFoundError

logger = logging.getLogger(__name__)
```

#### FastAPI App

```python
app = FastAPI()
```

---

#### Route 1: Health Check

```python
@app.get("/health")
async def health() -> dict:
    """Railway health check endpoint."""
    return {"status": "ok"}
```

**Test coverage:** `test_health_returns_ok`

---

#### Route 2: Meta Webhook Verification (GET)

```python
@app.get("/webhook/whatsapp/{client_id}")
async def verify_webhook(
    client_id: str,
    hub_mode: str = Query(alias="hub.mode", default=None),
    hub_challenge: str = Query(alias="hub.challenge", default=None),
    hub_verify_token: str = Query(alias="hub.verify_token", default=None),
) -> Response:
    """
    Meta webhook verification endpoint.
    
    Meta sends a GET request with:
    - hub.mode = "subscribe"
    - hub.challenge = random string to echo back
    - hub.verify_token = token to verify
    
    If token matches client's meta_verify_token, return hub.challenge as plain text.
    Otherwise return 403.
    """
    try:
        # Load client config
        client_config = load_client_config(client_id)
        
        # Verify token
        if hub_mode == "subscribe" and hub_verify_token == client_config.meta_verify_token:
            logger.info(f"Webhook verification successful for {client_id}")
            return PlainTextResponse(hub_challenge, status_code=200)
        else:
            logger.warning(f"Webhook verification failed for {client_id}: token mismatch")
            return Response(status_code=403)
    
    except ClientNotFoundError:
        logger.error(f"Webhook verification failed: unknown client {client_id}")
        return Response(status_code=403)
    
    except Exception as e:
        logger.error(f"Webhook verification error for {client_id}: {e}")
        return Response(status_code=403)
```

**Key rules:**
- Load `ClientConfig` via `load_client_config(client_id)`
- If `ClientNotFoundError` raised → return 403
- If `hub_mode == "subscribe"` AND `hub_verify_token == client_config.meta_verify_token` → return `PlainTextResponse(hub_challenge, status_code=200)`
- Else → return 403
- ANY exception → return 403 (never leak error details to Meta)

**Test coverage:**
- `test_verify_webhook_valid_token` — correct token → 200, returns challenge
- `test_verify_webhook_wrong_token` — wrong token → 403
- `test_verify_webhook_unknown_client` — unknown client_id → 403

---

#### Route 3: Receive Inbound WhatsApp Message (POST)

```python
@app.post("/webhook/whatsapp/{client_id}")
async def receive_whatsapp_message(
    client_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    """
    Receive inbound WhatsApp message from Meta Cloud API.
    
    CRITICAL RULE: ALWAYS return 200 OK to Meta, even on errors.
    Meta must never see 4xx or 5xx from this endpoint.
    """
    try:
        # Parse JSON body
        try:
            body = await request.json()
        except Exception as e:
            logger.error(f"Failed to parse webhook JSON for {client_id}: {e}")
            return Response(status_code=200)  # Return 200 even on parse error
        
        # Navigate to value
        try:
            value = body["entry"][0]["changes"][0]["value"]
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Invalid webhook structure for {client_id}: {e}")
            return Response(status_code=200)
        
        # Check if this is a status update (no messages key)
        if "messages" not in value:
            logger.info(f"Status update received for {client_id} — ignored")
            return Response(status_code=200)
        
        # Extract message data
        try:
            message = value["messages"][0]
            phone_number = message["from"]
            message_id = message["id"]
            message_type = message["type"]
            
            # Extract text — guard on type
            if message_type == "text":
                message_text = message["text"]["body"]
            else:
                # Non-text message (image, audio, etc.) — extract what we can
                message_text = ""
                logger.info(f"Non-text message type '{message_type}' from {phone_number}")
            
            # Extract contact info
            contact = value["contacts"][0]
            display_name = contact["profile"]["name"]
            wa_id = contact["wa_id"]
        
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Failed to extract message data for {client_id}: {e}")
            return Response(status_code=200)
        
        # Add background task (stub for Slice 2)
        logger.info(f"Spawning background task for {phone_number} (client: {client_id})")
        background_tasks.add_task(
            handle_inbound_message,
            client_id,
            phone_number,
            message_text,
        )
        
        # Return 200 immediately (before background task executes)
        return Response(status_code=200)
    
    except Exception as e:
        # Catch-all: log and return 200
        logger.error(f"Unexpected error in webhook POST for {client_id}: {e}", exc_info=True)
        return Response(status_code=200)
```

**Key rules:**
1. Parse `body = await request.json()` — wrap in try/except, return 200 on any error
2. Navigate: `value = body["entry"][0]["changes"][0]["value"]` — wrap in try/except, return 200 on any error
3. If `"messages"` not in `value` → return 200 immediately (status update — no processing)
4. Extract from `value["messages"][0]`:
   - `phone_number = message["from"]`
   - `message_id = message["id"]`
   - `message_type = message["type"]`
   - `message_text = message["text"]["body"]` (only if `type == "text"`)
   - `display_name = value["contacts"][0]["profile"]["name"]`
   - `wa_id = value["contacts"][0]["wa_id"]`
5. Add background task: `background_tasks.add_task(handle_inbound_message_stub, client_id, phone_number, message_text, message_type, message_id, display_name)`
6. Return `Response(status_code=200)` BEFORE background task executes
7. For unknown `client_id` or ANY exception: log, return 200 — Meta must ALWAYS receive 200

**Test coverage:**
- `test_post_valid_inbound_message_returns_200` — valid payload → 200
- `test_post_status_update_no_messages_returns_200` — status update → 200, no task
- `test_post_invalid_json_returns_200` — malformed JSON → 200
- `test_post_unknown_client_returns_200` — unknown client_id → 200
- `test_post_extracts_phone_number` — verify extraction logic
- `test_post_non_text_message_returns_200` — image message → 200

---

#### Background Task Stub

**CRITICAL:** The function MUST be named `handle_inbound_message` (NOT `handle_inbound_message_stub`).
The test file patches `engine.api.webhook.handle_inbound_message` — if the name differs, tests will fail.

```python
async def handle_inbound_message(
    client_id: str,
    phone_number: str,
    message_text: str,
) -> None:
    """
    Stub for message handling — Slice 3 replaces with real message_handler.
    
    For Slice 2, just log that the background task started.
    The signature accepts only (client_id, phone_number, message_text) — 
    background_tasks.add_task must pass exactly these three args.
    """
    logger.info(
        "[%s] Background task started for %s: %s",
        client_id,
        phone_number,
        message_text[:50],
    )
```

**Purpose:** This is a placeholder. Slice 3 will replace this function with a call to `handle_inbound_message()` from `engine.core.message_handler`.

---

### `engine/integrations/meta_whatsapp.py`

For Slice 2, create this file with only `verify_webhook_token()`. `send_message()` is added in Slice 3.

```python
"""
Meta Cloud API integration for WhatsApp.

Slice 2: verify_webhook_token() only
Slice 3: adds send_message()
"""
import logging
from engine.config.client_config import ClientConfig

logger = logging.getLogger(__name__)


async def verify_webhook_token(
    client_config: ClientConfig,
    hub_verify_token: str,
) -> bool:
    """
    Verify Meta webhook token against client's configured token.
    
    Args:
        client_config: Client configuration with meta_verify_token
        hub_verify_token: Token sent by Meta in GET request
    
    Returns:
        True if tokens match, False otherwise
    """
    return hub_verify_token == client_config.meta_verify_token
```

**Note:** This function is defined for completeness but is NOT directly called in Slice 2 (the verification logic is inline in `verify_webhook()` for simplicity). It can be refactored to use this function in a future slice if desired.

---

## Meta Webhook Payload Structure (Reference)

### Valid inbound message payload

```json
{
  "entry": [{
    "changes": [{
      "value": {
        "messages": [{
          "from": "6591234567",
          "id": "wamid.xxx",
          "type": "text",
          "text": {"body": "Hello, I need aircon servicing"}
        }],
        "contacts": [{
          "profile": {"name": "John Tan"},
          "wa_id": "6591234567"
        }]
      }
    }]
  }]
}
```

### Status update payload (no messages key)

```json
{
  "entry": [{
    "changes": [{
      "value": {
        "statuses": [{"status": "delivered", "id": "wamid.xxx"}]
      }
    }]
  }]
}
```

**Rule:** If `"messages"` is not in `value`, return 200 immediately with no processing.

---

## Package Dependencies

Add to `engine/requirements.txt` (if not already present):

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
httpx==0.27.0
```

For testing (if not already present):

```
pytest==8.3.0
pytest-asyncio==0.24.0
```

---

## Validation Commands

After implementation, run these commands to verify:

### 1. Run Slice 2 tests only
```bash
python3 -m pytest engine/tests/unit/test_webhook.py -v
```

**Expected:** All 10 tests pass.

### 2. Run all Slice 1 + Slice 2 tests
```bash
python3 -m pytest engine/tests/unit/ -v
```

**Expected:** All 22 tests pass (12 from Slice 1 + 10 from Slice 2).

### 3. Confirm eval tests unaffected
```bash
python3 -m pytest engine/tests/eval/ -v
```

**Expected:** 50 passed, 12 skipped (same as before Slice 2).

---

## Format Command

Before committing, run:

```bash
black engine/ --line-length 100
```

Or if using Ruff:

```bash
ruff format engine/
```

**Note:** @software-engineer has `bash: false` and cannot run this command. @sdet-engineer will run it during Phase 2 verification.

---

## Key Constraints (Must Follow)

1. **Meta MUST ALWAYS receive 200 OK from POST route** — catch all exceptions, never propagate to FastAPI error handler
2. **Background task is a stub** — do NOT import from `message_handler` (that's Slice 3)
3. **Status updates must be ignored** — if `"messages"` not in `value`, return 200 immediately
4. **Non-text messages** — extract what you can, pass `message_text = ""` to background task, still return 200
5. **Use `logging.getLogger(__name__)`** — no print statements
6. **All routes are async** — use `async def` throughout
7. **Import `load_client_config` from `engine.config.client_config`** — it's already implemented in Slice 1

---

## Test Files Location

All tests already created by @sdet-engineer:
- `engine/tests/unit/test_webhook.py` — 10 test cases
- `engine/tests/conftest.py` — updated with new fixtures

**Test fixtures used:**
- `sample_meta_payload` — valid inbound message
- `sample_meta_status_payload` — status update (no messages)
- `mock_client_config_obj` — mock ClientConfig for tests

---

## Architecture Reference

See `docs/architecture/engine_build_spec.md` Section 1 (Slice 2) for full context.

See `docs/architecture/00_platform_architecture.md` Section 4 (Component 1) for webhook flow diagram.

---

## Success Criteria

- [ ] All 3 routes implemented: GET /health, GET /webhook/whatsapp/{client_id}, POST /webhook/whatsapp/{client_id}
- [ ] POST route ALWAYS returns 200 OK (even on errors)
- [ ] Status updates ignored (no background task spawned)
- [ ] Valid inbound messages spawn background task (stub)
- [ ] Non-text messages handled gracefully
- [ ] Unknown client_id handled gracefully
- [ ] All 10 Slice 2 tests pass
- [ ] All 12 Slice 1 tests still pass (no regressions)
- [ ] Eval tests unaffected (50 passed, 12 skipped)
- [ ] Code formatted with Black/Ruff

---

**Ready for implementation.**
