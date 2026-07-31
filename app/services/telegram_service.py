"""
Telegram Notification Service

Sends published announcements to subscribed students via a Telegram bot.

How it works:
- Students register by messaging the bot with /start
- The bot stores their chat_id in a local SQLite table
- When an admin publishes an announcement, this service sends it to all
  registered chat IDs

Setup:
1. Set TELEGRAM_BOT_TOKEN in .env
2. Students message the bot on Telegram with /start to subscribe
3. Announcements are auto-sent on publish

The bot token is NEVER committed to source code — it lives only in .env.
"""

import logging
import os
import sqlite3
import threading
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_DB_PATH = os.path.join(_DATA_DIR, "telegram_subscribers.db")
_LOCK = threading.Lock()

TELEGRAM_API_BASE = "https://api.telegram.org/bot"


def _get_token() -> Optional[str]:
    """Read the bot token from environment (never hardcoded)."""
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() or None


def _connect() -> sqlite3.Connection:
    os.makedirs(_DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the subscribers table if it doesn't exist."""
    with _LOCK, _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS telegram_subscribers (
                chat_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                subscribed_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
    logger.info("Telegram subscribers DB initialized at %s", _DB_PATH)


def add_subscriber(chat_id: int, username: Optional[str] = None, first_name: Optional[str] = None) -> None:
    """Register a chat_id as a subscriber (idempotent)."""
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO telegram_subscribers (chat_id, username, first_name) VALUES (?, ?, ?)",
            (chat_id, username, first_name),
        )
    logger.info("Telegram subscriber added: %s (%s)", chat_id, username or first_name or "unknown")


def remove_subscriber(chat_id: int) -> None:
    """Unsubscribe a chat_id."""
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM telegram_subscribers WHERE chat_id = ?", (chat_id,))


def get_all_subscribers() -> List[int]:
    """Return all registered chat IDs."""
    with _LOCK, _connect() as conn:
        rows = conn.execute("SELECT chat_id FROM telegram_subscribers").fetchall()
    return [row["chat_id"] for row in rows]


def send_message(chat_id: int, text: str) -> bool:
    """Send a message to a single chat_id. Returns True on success."""
    token = _get_token()
    if not token:
        logger.warning("Telegram bot token not configured — skipping send.")
        return False

    url = f"{TELEGRAM_API_BASE}{token}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }, timeout=10)
        if resp.status_code == 200:
            return True
        else:
            logger.warning("Telegram send failed (chat=%s): %s", chat_id, resp.text[:200])
            return False
    except Exception as e:
        logger.error("Telegram send error: %s", e)
        return False


def broadcast_announcement(title: str, message: str, priority: str = "Normal", target_audience: str = "All Users") -> int:
    """
    Send an announcement to all Telegram subscribers.
    Returns the number of successful deliveries.
    """
    token = _get_token()
    if not token:
        logger.warning("Telegram bot token not configured — announcement not broadcast.")
        return 0

    subscribers = get_all_subscribers()
    if not subscribers:
        logger.info("No Telegram subscribers — skipping broadcast.")
        return 0

    # Format the message
    priority_emoji = "🚨" if priority == "Critical" else "📢"
    formatted = (
        f"{priority_emoji} <b>{title}</b>\n\n"
        f"{message}\n\n"
        f"<i>Target: {target_audience}</i>\n"
        f"— IOAI 2027 AI Concierge"
    )

    sent = 0
    for chat_id in subscribers:
        if send_message(chat_id, formatted):
            sent += 1

    logger.info("Telegram broadcast: %d/%d delivered (%s)", sent, len(subscribers), title[:40])
    return sent


def poll_updates() -> None:
    """
    Poll for new /start messages and register subscribers.
    Called periodically or on startup to pick up new subscribers.
    """
    token = _get_token()
    if not token:
        return

    url = f"{TELEGRAM_API_BASE}{token}/getUpdates"
    try:
        resp = requests.get(url, params={"timeout": 5, "allowed_updates": '["message"]'}, timeout=10)
        if resp.status_code != 200:
            return

        data = resp.json()
        updates = data.get("result", [])
        last_update_id = None

        for update in updates:
            last_update_id = update["update_id"]
            msg = update.get("message", {})
            text = msg.get("text", "")
            chat = msg.get("chat", {})
            chat_id = chat.get("id")

            if not chat_id:
                continue

            if text.strip().lower() == "/start":
                username = msg.get("from", {}).get("username")
                first_name = msg.get("from", {}).get("first_name")
                add_subscriber(chat_id, username, first_name)
                send_message(chat_id, "✅ You're now subscribed to IOAI 2027 announcements! You'll receive notifications when organisers publish new updates.\n\nSend /stop to unsubscribe.")

            elif text.strip().lower() == "/stop":
                remove_subscriber(chat_id)
                send_message(chat_id, "🔕 You've been unsubscribed from IOAI 2027 announcements.")

        # Acknowledge processed updates
        if last_update_id is not None:
            requests.get(url, params={"offset": last_update_id + 1, "timeout": 1}, timeout=5)

    except Exception as e:
        logger.debug("Telegram poll error (non-critical): %s", e)
