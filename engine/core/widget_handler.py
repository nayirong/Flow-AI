"""
Widget message handler — mirrors WhatsApp message_handler.py pipeline for web widget.

Pipeline:
    1. Load client config + DB connection
    2. Log inbound to interactions_log
    3. Escalation gate — query visitors table
    4. If escalation_flag=True: log holding reply, return (HOLDING_REPLY, True)
    5. Fetch conversation history from interactions_log
    6. Build system message from config/policies
    7. Call agent with tool definitions
    8. Log outbound reply
    9. Return (reply_text, was_escalated)
"""
import logging
from typing import Tuple

from engine.config.client_config import load_client_config
from engine.integrations.supabase_client import get_client_db
from engine.core.context_builder import build_system_message
from engine.core.agent_runner import run_agent
from engine.core.tools import build_tool_definitions, build_tool_dispatch

logger = logging.getLogger(__name__)

HOLDING_REPLY = (
    "Thank you for reaching out. "
    "A member of our team will get back to you today."
)


async def handle_widget_message(
    client_id: str,
    session_id: str,
    message: str,
) -> Tuple[str, bool]:
    """
    Process a widget message through the agent pipeline.

    Args:
        client_id: Client identifier
        session_id: Widget session ID
        message: User message text

    Returns:
        Tuple of (reply_text, was_escalated)
    """
    # 1. Get client DB and config
    client_db = await get_client_db(client_id)
    client_config = await load_client_config(client_id)

    # 2. Log inbound to interactions_log
    try:
        await client_db.table("interactions_log").insert({
            "channel": "widget",
            "session_id": session_id,
            "phone_number": None,
            "role": "user",
            "content": message,
            "message_text": message,
            "direction": "inbound",
        }).execute()
    except Exception as e:
        logger.error(
            f"Failed to log inbound widget message for {client_id} session {session_id}: {e}",
            exc_info=True,
        )
        # Continue anyway — logging failure should not stop message processing

    # 3. Escalation gate — check visitors table
    try:
        visitor_result = await client_db.table("visitors").select(
            "escalation_flag"
        ).eq("session_id", session_id).limit(1).execute()

        if visitor_result.data and visitor_result.data[0].get("escalation_flag") is True:
            # Log outbound holding reply
            try:
                await client_db.table("interactions_log").insert({
                    "channel": "widget",
                    "session_id": session_id,
                    "phone_number": None,
                    "role": "assistant",
                    "content": HOLDING_REPLY,
                    "message_text": HOLDING_REPLY,
                    "direction": "outbound",
                }).execute()
            except Exception as e:
                logger.error(
                    f"Failed to log escalation holding reply for {client_id} session {session_id}: {e}",
                    exc_info=True,
                )
            return (HOLDING_REPLY, True)
    except Exception as e:
        logger.error(
            f"Failed to check escalation gate for {client_id} session {session_id}: {e}",
            exc_info=True,
        )
        # On escalation gate failure, continue to agent rather than blocking

    # 4. Fetch conversation history (last 40 rows = 20 exchanges)
    try:
        history_result = await client_db.table("interactions_log").select(
            "message_text, direction, created_at"
        ).eq("session_id", session_id).eq("channel", "widget").order(
            "created_at", desc=True
        ).limit(40).execute()

        history_rows = history_result.data or []
    except Exception as e:
        logger.error(
            f"Failed to fetch conversation history for {client_id} session {session_id}: {e}",
            exc_info=True,
        )
        history_rows = []

    # 5. Format as Claude messages list (reverse to chronological order)
    messages = []
    for row in reversed(history_rows):
        role = "user" if row["direction"] == "inbound" else "assistant"
        content = row.get("message_text", "")
        if content:
            messages.append({"role": role, "content": content})

    # 5a. Cross-channel history: if visitor has a linked WhatsApp customer, prepend prior history
    try:
        visitor_result = await client_db.table("visitors").select(
            "customer_id"
        ).eq("session_id", session_id).limit(1).execute()

        visitor_rows = visitor_result.data or []
        if visitor_rows and visitor_rows[0].get("customer_id"):
            customer_id = visitor_rows[0]["customer_id"]
            # Get customer phone_number
            customer_result = await client_db.table("customers").select(
                "phone_number"
            ).eq("id", customer_id).limit(1).execute()

            if customer_result.data:
                phone_number = customer_result.data[0]["phone_number"]
                # Fetch last 5 WhatsApp exchanges (10 rows)
                wa_history_result = await client_db.table("interactions_log").select(
                    "message_text, direction, created_at"
                ).eq("phone_number", phone_number).eq("channel", "whatsapp").order(
                    "created_at", desc=True
                ).limit(10).execute()

                wa_rows = list(reversed(wa_history_result.data or []))
                if wa_rows:
                    # Prepend WhatsApp history BEFORE widget history
                    wa_messages = []
                    for row in wa_rows:
                        role = "user" if row["direction"] == "inbound" else "assistant"
                        content = row.get("message_text", "")
                        if content:
                            wa_messages.append({"role": role, "content": f"[Prior WhatsApp] {content}"})
                    
                    messages = wa_messages + messages  # Prepend to front
                    logger.info(
                        f"Prepended {len(wa_messages)} WhatsApp messages for session {session_id} "
                        f"(customer {customer_id})"
                    )
    except Exception as e:
        logger.warning(f"Cross-channel history fetch failed for session {session_id}: {e}")
        # Non-fatal — continue without cross-channel history

    # 6. Build system message from config/policies
    try:
        system_message = await build_system_message(client_db)
    except Exception as e:
        logger.error(
            f"Failed to build system message for {client_id}: {e}",
            exc_info=True,
        )
        # Return safe error message if context builder fails
        error_reply = (
            "We're experiencing a technical issue right now. "
            "Please try again in a moment."
        )
        try:
            await client_db.table("interactions_log").insert({
                "channel": "widget",
                "session_id": session_id,
                "phone_number": None,
                "role": "assistant",
                "content": error_reply,
                "message_text": error_reply,
                "direction": "outbound",
            }).execute()
        except:
            pass
        return (error_reply, False)

    # 7. Build tool definitions and dispatch
    tool_definitions = build_tool_definitions(pending_booking=None)
    # Widget sessions don't have phone numbers; use session_id as identifier
    tool_dispatch = build_tool_dispatch(
        db=client_db,
        client_config=client_config,
        phone_number=session_id,  # Use session_id as identifier for tools
        lead_time_days=2,
    )

    # 8. Call agent
    try:
        reply = await run_agent(
            system_message=system_message,
            messages=messages,
            tool_definitions=tool_definitions,
            tool_dispatch=tool_dispatch,
            client_id=client_id,
        )
    except Exception as e:
        logger.error(
            f"Agent call failed for {client_id} session {session_id}: {e}",
            exc_info=True,
        )
        reply = (
            "I'm sorry, I wasn't able to complete your request right now. "
            "Please try again in a moment."
        )

    # 9. Log outbound reply
    try:
        await client_db.table("interactions_log").insert({
            "channel": "widget",
            "session_id": session_id,
            "phone_number": None,
            "role": "assistant",
            "content": reply,
            "message_text": reply,
            "direction": "outbound",
        }).execute()
    except Exception as e:
        logger.error(
            f"Failed to log outbound widget message for {client_id} session {session_id}: {e}",
            exc_info=True,
        )

    return (reply, False)
