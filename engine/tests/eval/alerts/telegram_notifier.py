"""
TelegramNotifier: Sends alerts via Telegram bot API.

Uses direct HTTP to api.telegram.org (no Telegram SDK).

Features:
- Rate limiting (3-second delay between sends)
- Message truncation (4096 char limit)
- Markdown formatting
- Thread support (optional message_thread_id)
"""

import asyncio
import time
import logging
from typing import Optional

import httpx

from .base import BaseNotifier
from ..models import AlertPayload


logger = logging.getLogger(__name__)


class TelegramNotifier(BaseNotifier):
    """
    Telegram alert notifier via direct HTTP.
    
    Rate limits: 1 message per 3 seconds.
    Message length: Truncates at 4096 chars.
    """
    
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        thread_id: Optional[str] = None,
    ):
        """
        Initialize with Telegram credentials.
        
        Args:
            bot_token: Telegram bot token
            chat_id: Telegram chat/channel ID
            thread_id: Optional message thread ID (for topics)
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.thread_id = thread_id
        self.last_send_time = 0.0
    
    async def send_alert(self, alert: AlertPayload) -> bool:
        """
        Format alert and send via Telegram sendMessage API.
        
        Returns:
            True if HTTP 200 received, False otherwise.
        """
        try:
            message = self._format_alert(alert)
            return await self._send_message(message)
        except Exception as e:
            logger.error(f"TelegramNotifier.send_alert() failed: {e}")
            return False
    
    async def _send_message(self, text: str) -> bool:
        """
        POST to https://api.telegram.org/bot{token}/sendMessage
        
        Body:
        {
          "chat_id": "{chat_id}",
          "message_thread_id": "{thread_id}" (optional),
          "text": "{text}",
          "parse_mode": "Markdown"
        }
        
        Rate limiting: enforce 3-second delay between sends.
        Message length: truncate at 4096 chars (Telegram limit).
        
        Returns:
            True if HTTP 200 and ok=true, False otherwise.
        """
        try:
            # Rate limiting
            elapsed = time.monotonic() - self.last_send_time
            if elapsed < 3.0:
                await asyncio.sleep(3.0 - elapsed)
            
            # Truncate if needed
            if len(text) > 4096:
                text = text[:4093] + "..."
            
            # Build payload
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "Markdown"
            }
            
            # Add thread_id if set
            if self.thread_id:
                payload["message_thread_id"] = self.thread_id
            
            # Send request
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload)
            
            # Update last send time
            self.last_send_time = time.monotonic()
            
            # Check response
            if response.status_code == 200:
                data = response.json()
                if data.get("ok", False):
                    return True
                else:
                    logger.error(f"Telegram API returned ok=false: {data}")
                    return False
            else:
                logger.error(f"Telegram API returned {response.status_code}: {response.text}")
                return False
        
        except Exception as e:
            logger.error(f"TelegramNotifier._send_message() exception: {e}")
            return False
    
    def _format_alert(self, alert: AlertPayload) -> str:
        """
        Format AlertPayload as Markdown message.
        """
        lines = []
        lines.append("*Flow AI Eval Alert*")
        lines.append("")
        lines.append(f"*Type:* {alert.alert_type}")
        lines.append(f"*Environment:* {alert.environment}")
        lines.append(f"*Client:* {alert.client_id or 'all'}")
        lines.append(f"*Run:* {alert.run_id}")
        lines.append("")
        
        if alert.dimension:
            lines.append(f"*Dimension:* {alert.dimension}")
        else:
            lines.append("*Dimension:* N/A")
        
        if alert.score_before is not None:
            lines.append(f"*Score before:* {alert.score_before:.2f}")
        else:
            lines.append("*Score before:* N/A")
        
        if alert.score_after is not None:
            lines.append(f"*Score after:* {alert.score_after:.2f}")
        else:
            lines.append("*Score after:* N/A")
        
        lines.append("")
        
        if alert.failing_tests:
            lines.append("*Failing tests:*")
            for test in alert.failing_tests:
                lines.append(f"• {test}")
        
        lines.append("")
        lines.append(alert.message)
        
        if alert.report_url:
            lines.append("")
            lines.append(alert.report_url)
        
        return "\n".join(lines)
