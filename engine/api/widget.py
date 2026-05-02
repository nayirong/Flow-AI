"""
Widget API routes — Flow AI web chat widget endpoints.

Four routes:
    POST  /chat/{client_id}/session    → create session
    POST  /chat/{client_id}/message    → send message to agent
    GET   /chat/{client_id}/history    → fetch conversation history
    GET   /widget/{client_id}.js       → serve widget JS with inlined client_id
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from engine.config.client_config import load_client_config, ClientNotFoundError
from engine.integrations.supabase_client import get_client_db
from engine.core.widget_handler import handle_widget_message

logger = logging.getLogger(__name__)

widget_router = APIRouter()


# ── Helper functions ──────────────────────────────────────────────────────────


def _normalize_phone(phone: str) -> str:
    """Normalize phone number to E.164 without + (e.g. 6591234567)."""
    phone = re.sub(r"[\s\-\.]", "", phone)
    if phone.startswith("+"):
        phone = phone[1:]
    if len(phone) == 8 and phone[0] in "689":
        phone = "65" + phone
    return phone


# ── Request/Response models ───────────────────────────────────────────────────


class CreateSessionRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None  # E.164 format or local SG format


class CreateSessionResponse(BaseModel):
    session_id: str
    welcome_message: str


class SendMessageRequest(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1, max_length=2000)


class SendMessageResponse(BaseModel):
    reply: str
    escalated: bool


class HistoryMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    created_at: str


class HistoryResponse(BaseModel):
    messages: list[HistoryMessage]
    escalated: bool


# ── Routes ────────────────────────────────────────────────────────────────────


@widget_router.post("/chat/{client_id}/session", response_model=CreateSessionResponse)
async def create_session(client_id: str, request: CreateSessionRequest = CreateSessionRequest()):
    """
    Create a new widget session for the specified client.

    Body (optional):
        name: Visitor name
        email: Visitor email
        phone: Visitor phone (E.164 or local SG format)

    Returns:
        session_id and welcome_message
    """
    # Load client config
    try:
        client_config = await load_client_config(client_id)
    except ClientNotFoundError:
        raise HTTPException(status_code=404, detail="Client not found")
    except Exception as e:
        logger.error(f"Failed to load client config for {client_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

    # Check if widget is enabled
    if not client_config.widget_enabled:
        raise HTTPException(status_code=403, detail="Widget not enabled for this client")

    # Generate session ID
    session_id = str(uuid.uuid4())

    # Insert into sessions table
    try:
        client_db = await get_client_db(client_id)
        now = datetime.now(timezone.utc).isoformat()
        await client_db.table("sessions").insert({
            "session_id": session_id,
            "client_id": client_id,
            "created_at": now,
            "last_active_at": now,
        }).execute()
    except Exception as e:
        logger.error(f"Failed to create session for {client_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create session")

    # Identity linking: match phone to existing customer
    customer_id = None
    normalized_phone = None
    
    if request.phone:
        try:
            normalized_phone = _normalize_phone(request.phone)
            customer_result = await client_db.table("customers").select(
                "id"
            ).eq("phone_number", normalized_phone).limit(1).execute()
            
            if customer_result.data:
                customer_id = customer_result.data[0]["id"]
                logger.info(f"Linked session {session_id} to customer {customer_id} via phone {normalized_phone}")
        except Exception as e:
            # Identity lookup failure is non-fatal
            logger.warning(f"Failed to lookup customer for phone {request.phone}: {e}")

    # Insert into visitors table (always, even if no form data)
    try:
        await client_db.table("visitors").insert({
            "session_id": session_id,
            "client_id": client_id,
            "name": request.name,
            "email": request.email,
            "phone": normalized_phone,
            "customer_id": customer_id,
            "created_at": now,
        }).execute()
    except Exception as e:
        # Visitor creation failure is non-fatal (session still works)
        logger.error(f"Failed to create visitor for session {session_id}: {e}", exc_info=True)

    return CreateSessionResponse(
        session_id=session_id,
        welcome_message=client_config.widget_welcome_message,
    )


@widget_router.post("/chat/{client_id}/message", response_model=SendMessageResponse)
async def send_message(client_id: str, request: SendMessageRequest):
    """
    Send a message to the agent and get a reply.

    Body:
        session_id: Widget session ID
        message: User message (1-2000 chars)

    Returns:
        reply and escalated flag
    """
    # Load client config
    try:
        client_config = await load_client_config(client_id)
    except ClientNotFoundError:
        raise HTTPException(status_code=404, detail="Client not found")
    except Exception as e:
        logger.error(f"Failed to load client config for {client_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

    # Check if widget is enabled
    if not client_config.widget_enabled:
        raise HTTPException(status_code=403, detail="Widget not enabled for this client")

    # Validate session
    try:
        client_db = await get_client_db(client_id)
        session_result = await client_db.table("sessions").select(
            "session_id, expired_at"
        ).eq("session_id", request.session_id).eq("client_id", client_id).limit(1).execute()

        if not session_result.data:
            raise HTTPException(status_code=404, detail="Session not found")

        session_row = session_result.data[0]
        if session_row.get("expired_at") is not None:
            raise HTTPException(status_code=410, detail="Session expired")

        # Update last_active_at
        now = datetime.now(timezone.utc).isoformat()
        await client_db.table("sessions").update({
            "last_active_at": now,
        }).eq("session_id", request.session_id).execute()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to validate session {request.session_id} for {client_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

    # Handle message through agent pipeline
    try:
        reply_text, was_escalated = await handle_widget_message(
            client_id=client_id,
            session_id=request.session_id,
            message=request.message,
        )
        return SendMessageResponse(reply=reply_text, escalated=was_escalated)
    except Exception as e:
        logger.error(
            f"Widget message handler failed for {client_id} session {request.session_id}: {e}",
            exc_info=True,
        )
        # Never let exceptions propagate — return safe error message
        return SendMessageResponse(
            reply="We're experiencing a technical issue. Please try again in a moment.",
            escalated=False,
        )


@widget_router.get("/chat/{client_id}/history", response_model=HistoryResponse)
async def get_history(client_id: str, session_id: str = Query(...)):
    """
    Fetch conversation history for a widget session.

    Query params:
        session_id: Widget session ID (required)

    Returns:
        List of messages and escalation status
    """
    # Load client config
    try:
        client_config = await load_client_config(client_id)
    except ClientNotFoundError:
        raise HTTPException(status_code=404, detail="Client not found")
    except Exception as e:
        logger.error(f"Failed to load client config for {client_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

    # Check if widget is enabled
    if not client_config.widget_enabled:
        raise HTTPException(status_code=403, detail="Widget not enabled for this client")

    # Validate session
    try:
        client_db = await get_client_db(client_id)
        session_result = await client_db.table("sessions").select(
            "session_id, expired_at"
        ).eq("session_id", session_id).eq("client_id", client_id).limit(1).execute()

        if not session_result.data:
            raise HTTPException(status_code=404, detail="Session not found")

        session_row = session_result.data[0]
        if session_row.get("expired_at") is not None:
            raise HTTPException(status_code=410, detail="Session expired")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to validate session {session_id} for {client_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

    # Query interactions_log
    try:
        history_result = await client_db.table("interactions_log").select(
            "message_text, direction, created_at"
        ).eq("session_id", session_id).eq("channel", "widget").order(
            "created_at", desc=False
        ).limit(50).execute()

        history_rows = history_result.data or []
    except Exception as e:
        logger.error(f"Failed to fetch history for {client_id} session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch history")

    # Map to response format
    messages = []
    for row in history_rows:
        role = "user" if row["direction"] == "inbound" else "assistant"
        content = row.get("message_text", "")
        created_at = row.get("created_at", "")
        if content:
            messages.append(HistoryMessage(
                role=role,
                content=content,
                created_at=created_at,
            ))

    # Query visitors table for escalation status
    escalated = False
    try:
        visitor_result = await client_db.table("visitors").select(
            "escalation_flag"
        ).eq("session_id", session_id).limit(1).execute()

        if visitor_result.data and visitor_result.data[0].get("escalation_flag") is True:
            escalated = True
    except Exception as e:
        logger.error(f"Failed to check escalation status for {client_id} session {session_id}: {e}")
        # Continue anyway — escalation check failure should not block history

    return HistoryResponse(messages=messages, escalated=escalated)


@widget_router.get("/widget/{client_id}.js")
async def serve_widget_js(client_id: str):
    """
    Serve widget JavaScript with inlined client_id.

    Returns:
        JavaScript file with Content-Type: application/javascript
    """
    # Load client config
    try:
        client_config = await load_client_config(client_id)
    except ClientNotFoundError:
        return Response(
            content="// Widget not enabled",
            media_type="application/javascript",
            status_code=404,
        )
    except Exception as e:
        logger.error(f"Failed to load client config for {client_id}: {e}")
        return Response(
            content="// Internal server error",
            media_type="application/javascript",
            status_code=500,
        )

    # Check if widget is enabled
    if not client_config.widget_enabled:
        return Response(
            content="// Widget not enabled",
            media_type="application/javascript",
            status_code=404,
        )

    # Read widget.js file
    widget_js_path = Path(__file__).parent.parent / "static" / "widget.js"
    try:
        widget_js_content = widget_js_path.read_text()
    except FileNotFoundError:
        # Create placeholder if file doesn't exist yet
        widget_js_content = (
            "// Flow AI Chat Widget — Phase 1 Placeholder\n"
            "// Full widget JS is built in Slice 4 (widget-04-js branch)\n"
            "console.log('[FlowAI] Widget JS loaded for client:', window.FLOWAI_CLIENT_ID);\n"
        )
    except Exception as e:
        logger.error(f"Failed to read widget.js: {e}")
        return Response(
            content="// Failed to load widget",
            media_type="application/javascript",
            status_code=500,
        )

    # Prepend client config injection
    # Validate hex color
    primary_color = client_config.widget_primary_color or "#1B5E3F"
    if not re.match(r'^#[0-9A-Fa-f]{6}$', primary_color):
        logger.warning(
            f"Invalid widget_primary_color '{primary_color}' for client {client_id}. "
            f"Falling back to #1B5E3F"
        )
        primary_color = "#1B5E3F"

    # Validate and truncate icon
    button_icon = client_config.widget_button_icon or "💬"
    if len(button_icon) > 4:
        logger.warning(
            f"widget_button_icon for client {client_id} exceeds 4 chars. "
            f"Truncating to '{button_icon[:4]}'"
        )
        button_icon = button_icon[:4]

    # Inject config object — widget.js reads from window.FLOWAI_CONFIG
    config_block = (
        f'window.FLOWAI_CONFIG = {{'
        f'"clientId": "{client_id}", '
        f'"primaryColor": "{primary_color}", '
        f'"buttonIcon": "{button_icon}"'
        f'}};\n'
    )
    js_with_client_id = config_block + widget_js_content

    return Response(
        content=js_with_client_id.encode("utf-8"),
        media_type="application/javascript; charset=utf-8",
        headers={"Cache-Control": "public, max-age=3600"},
    )
