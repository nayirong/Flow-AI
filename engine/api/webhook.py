"""
FastAPI webhook receiver for Meta Cloud API (WhatsApp).

Routes:
    GET  /health                              — Railway health check
    GET  /webhook/whatsapp/{client_id}        — Meta webhook verification
    POST /webhook/whatsapp/{client_id}        — Receive inbound WhatsApp messages

CRITICAL RULE: POST route MUST always return 200 OK to Meta.
Meta will disable the webhook if it receives 4xx/5xx responses.
"""
import logging

from fastapi import FastAPI, Request, BackgroundTasks, Query, Response
from fastapi.responses import PlainTextResponse

from engine.config.client_config import load_client_config, ClientNotFoundError
from engine.core.message_handler import handle_inbound_message

logger = logging.getLogger(__name__)

app = FastAPI()


# ---------------------------------------------------------------------------
# Route 1 — Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    """Railway health check endpoint."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Route 2 — Meta webhook verification (GET)
# ---------------------------------------------------------------------------

@app.get("/webhook/whatsapp/{client_id}")
async def verify_webhook(
    client_id: str,
    hub_mode: str = Query(alias="hub.mode", default=None),
    hub_challenge: str = Query(alias="hub.challenge", default=None),
    hub_verify_token: str = Query(alias="hub.verify_token", default=None),
) -> Response:
    """
    Meta webhook verification handshake.

    Meta sends a GET with hub.mode=subscribe, hub.challenge, and hub.verify_token.
    If the token matches the client's configured token, return hub.challenge as plain text.
    Return 403 on any mismatch or error.
    """
    try:
        client_config = await load_client_config(client_id)

        if hub_mode == "subscribe" and hub_verify_token == client_config.meta_verify_token:
            logger.info(f"Webhook verification successful for client '{client_id}'")
            return PlainTextResponse(hub_challenge, status_code=200)

        logger.warning(
            f"Webhook verification failed for client '{client_id}': "
            f"hub_mode={hub_mode!r}, token_match={hub_verify_token == client_config.meta_verify_token}"
        )
        return Response(status_code=403)

    except ClientNotFoundError:
        logger.warning(f"Webhook verification failed: unknown client '{client_id}'")
        return Response(status_code=403)

    except Exception as e:
        logger.error(f"Webhook verification error for client '{client_id}': {e}", exc_info=True)
        return Response(status_code=403)


# ---------------------------------------------------------------------------
# Route 3 — Receive inbound WhatsApp message (POST)
# ---------------------------------------------------------------------------

@app.post("/webhook/whatsapp/{client_id}")
async def receive_whatsapp_message(
    client_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    """
    Receive inbound WhatsApp message from Meta Cloud API.

    CRITICAL: ALWAYS returns 200 OK to Meta, even on errors.
    Meta must never see 4xx or 5xx from this endpoint or it will disable the webhook.
    """
    try:
        # 1. Parse JSON body
        try:
            body = await request.json()
        except Exception as e:
            logger.error(f"Failed to parse webhook JSON for client '{client_id}': {e}")
            return Response(status_code=200)

        # 2. Navigate to the value object
        try:
            value = body["entry"][0]["changes"][0]["value"]
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Invalid webhook structure for client '{client_id}': {e}")
            return Response(status_code=200)

        # 3. Status update — no messages key — ignore
        if "messages" not in value:
            logger.info(f"Status update received for client '{client_id}' — ignored")
            return Response(status_code=200)

        # 4. Extract message data
        try:
            message = value["messages"][0]
            phone_number = message["from"]
            message_id = message["id"]
            message_type = message["type"]
            
            # Extract context.id for reply-to-message detection
            context_message_id = message.get("context", {}).get("id")

            if message_type == "text":
                message_text = message["text"]["body"]
            else:
                # Non-text message (image, audio, sticker, etc.) — pass empty string
                message_text = ""
                logger.info(
                    f"Non-text message type '{message_type}' from {phone_number} "
                    f"(client: {client_id}) — processing with empty text"
                )

            contact = value["contacts"][0]
            display_name = contact["profile"]["name"]

        except (KeyError, IndexError, TypeError) as e:
            logger.error(
                f"Failed to extract message fields for client '{client_id}': {e}"
            )
            return Response(status_code=200)

        # 5. Spawn background task — runs after 200 is returned to Meta
        logger.info(f"Spawning background task for {phone_number} (client: {client_id})")
        background_tasks.add_task(
            handle_inbound_message,
            client_id,
            phone_number,
            message_text,
            message_type,
            message_id,
            display_name,
            context_message_id,
        )

        # 6. Return 200 immediately — before background task executes
        return Response(status_code=200)

    except Exception as e:
        # Catch-all safety net — Meta must always receive 200
        logger.error(
            f"Unexpected error in POST webhook for client '{client_id}': {e}",
            exc_info=True,
        )
        return Response(status_code=200)
