"""
Meta Cloud API integration for WhatsApp.

Slice 2: verify_webhook_token()
Slice 3: send_message()
"""
import logging

import httpx

from engine.config.client_config import ClientConfig

logger = logging.getLogger(__name__)


async def verify_webhook_token(
    client_config: ClientConfig,
    hub_verify_token: str,
) -> bool:
    """
    Verify Meta webhook token against client's configured token.

    Args:
        client_config: Client configuration containing meta_verify_token.
        hub_verify_token: Token received from Meta in the GET verification request.

    Returns:
        True if tokens match, False otherwise.
    """
    return hub_verify_token == client_config.meta_verify_token


async def send_message(
    client_config: ClientConfig,
    to_phone_number: str,
    text: str,
) -> bool:
    """
    Send a WhatsApp text message via Meta Cloud API.

    Args:
        client_config:   Client configuration with Meta credentials.
        to_phone_number: Recipient phone number (E.164 without +, e.g. "6591234567").
        text:            Message body text.

    Returns:
        True if message sent successfully, False otherwise.
        Never raises — caller checks return value.
    """
    url = (
        f"https://graph.facebook.com/v19.0/"
        f"{client_config.meta_phone_number_id}/messages"
    )
    headers = {
        "Authorization": f"Bearer {client_config.meta_whatsapp_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone_number,
        "type": "text",
        "text": {"body": text},
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            response = await http_client.post(url, headers=headers, json=payload)

        if response.status_code == 200:
            logger.info(f"Message sent successfully to {to_phone_number}")
            return True

        logger.error(
            f"Meta API error sending to {to_phone_number}: "
            f"status={response.status_code}, body={response.text[:200]}"
        )
        return False

    except Exception as e:
        logger.error(
            f"Failed to send WhatsApp message to {to_phone_number}: {e}",
            exc_info=True,
        )
        return False
