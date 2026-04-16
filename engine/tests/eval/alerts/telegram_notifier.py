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
from typing import Optional

from .base import BaseNotifier, AlertPayload


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
        # TODO: initialize httpx.AsyncClient
    
    async def send_alert(self, alert: AlertPayload) -> bool:
        """
        Format alert and send via Telegram sendMessage API.
        
        Returns:
            True if HTTP 200 received, False otherwise.
        """
        # TODO: implement
        # - Format alert via _format_alert()
        # - Send message via _send_message()
        # - Return True/False based on success
        # - Never raise
        
        raise NotImplementedError("TelegramNotifier.send_alert() not yet implemented")
    
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
        # TODO: implement
        # - Enforce rate limiting (check last_send_time)
        # - Truncate message if > 4096 chars
        # - Build payload
        # - POST to api.telegram.org
        # - Return True/False
        # - Never raise
        
        raise NotImplementedError()
    
    def _format_alert(self, alert: AlertPayload) -> str:
        """
        Format AlertPayload as Markdown message.
        
        Template:
        
        🚨 *Flow AI Eval Alert*
        
        📉 *Regression Detected*
        **Client:** hey-aircon
        **Run ID:** `2026-04-16T02:00:00Z-abc123`
        
        **Dimension:** tool_use
        **Score:** 0.94 → 0.86 (-8%)
        **Safety:** ✅ Pass
        
        **Failed Tests (5):**
        • booking_happy_path_am_slot
        • reschedule_policy_same_day
        ...and 3 more
        
        [View Report](https://github.com/...)
        [View Trace](https://langfuse.com/...) *(Phase 2)*
        """
        # TODO: implement formatting
        raise NotImplementedError()
