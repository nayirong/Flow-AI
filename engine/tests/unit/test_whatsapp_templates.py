"""Unit tests for WhatsApp template message functions."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from engine.integrations.meta_whatsapp import send_template_message, send_alert_to_human


def _make_client_config(template_name=None):
    cfg = MagicMock()
    cfg.meta_phone_number_id = "1234567890"
    cfg.meta_whatsapp_token = "test_token"
    cfg.client_id = "test-client"
    cfg.template_escalation_alert = template_name
    return cfg


@pytest.mark.asyncio
async def test_send_template_message_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"messages": [{"id": "wamid.test123"}]}

    with patch("engine.integrations.meta_whatsapp.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        cfg = _make_client_config()
        result = await send_template_message(
            client_config=cfg,
            to_phone_number="6591234567",
            template_name="escalation_alert",
            language_code="en_US",
            components=[{"type": "body", "parameters": [{"type": "text", "text": "test"}]}],
        )
    assert result == "wamid.test123"


@pytest.mark.asyncio
async def test_send_template_message_meta_error():
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"

    with patch("engine.integrations.meta_whatsapp.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        cfg = _make_client_config()
        result = await send_template_message(
            client_config=cfg,
            to_phone_number="6591234567",
            template_name="escalation_alert",
            language_code="en_US",
            components=[],
        )
    assert result is None


@pytest.mark.asyncio
async def test_send_template_message_exception():
    with patch("engine.integrations.meta_whatsapp.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
        mock_client_cls.return_value = mock_client

        cfg = _make_client_config()
        result = await send_template_message(
            client_config=cfg,
            to_phone_number="6591234567",
            template_name="escalation_alert",
            language_code="en_US",
            components=[],
        )
    assert result is None


@pytest.mark.asyncio
async def test_send_alert_to_human_uses_template_when_configured():
    cfg = _make_client_config(template_name="escalation_alert")

    with patch("engine.integrations.meta_whatsapp.send_template_message", new_callable=AsyncMock) as mock_template, \
         patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock) as mock_free:
        mock_template.return_value = "wamid.template123"
        result = await send_alert_to_human(
            client_config=cfg,
            to_phone_number="6580235587",
            template_name=cfg.template_escalation_alert,
            template_variables=["HeyAircon", "6582829071", "Requested discount"],
            fallback_text="fallback text",
            alert_label="escalation_alert",
        )
    mock_template.assert_called_once()
    mock_free.assert_not_called()
    assert result == "wamid.template123"


@pytest.mark.asyncio
async def test_send_alert_to_human_falls_back_to_free_text_when_not_configured():
    cfg = _make_client_config(template_name=None)

    with patch("engine.integrations.meta_whatsapp.send_template_message", new_callable=AsyncMock) as mock_template, \
         patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock) as mock_free:
        mock_free.return_value = "wamid.free123"
        result = await send_alert_to_human(
            client_config=cfg,
            to_phone_number="6580235587",
            template_name=None,
            template_variables=[],
            fallback_text="fallback text",
            alert_label="escalation_alert",
        )
    mock_template.assert_not_called()
    mock_free.assert_called_once()
    assert result == "wamid.free123"


@pytest.mark.asyncio
async def test_send_alert_no_fallback_on_template_failure():
    cfg = _make_client_config(template_name="escalation_alert")

    with patch("engine.integrations.meta_whatsapp.send_template_message", new_callable=AsyncMock) as mock_template, \
         patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock) as mock_free:
        mock_template.return_value = None  # template send failed
        result = await send_alert_to_human(
            client_config=cfg,
            to_phone_number="6580235587",
            template_name="escalation_alert",
            template_variables=["HeyAircon", "6582829071", "reason"],
            fallback_text="fallback",
            alert_label="escalation_alert",
        )
    mock_free.assert_not_called()
    assert result is None
