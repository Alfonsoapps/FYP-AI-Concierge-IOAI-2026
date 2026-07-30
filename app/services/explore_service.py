"""
Explore Service Module (Participant Experience Features)

Backs the "Explore" tab: Singapore culture/food/etiquette guidance content
(Requirements F10R1, F10R2, F10R3) and optional gamified exploration
challenges, achievement badges, and cultural learning activities
(Requirements F10R4, F10R5, F10R6).

Design notes:
    - The culture guide (facts, food recommendations, etiquette tips) is
      static reference content. It is exposed via the API for the Explore
      page AND blended into the AI concierge's context (see
      `app/services/ai_service.py::_culture_context`) so the assistant can
      answer culture/food/etiquette questions directly in chat.
    - Challenges and cultural learning activities share one catalog
      (`EXPLORE_ITEMS`), distinguished by `item_type`. Completing an item
      awards its badge. Completing every item of a given type awards a bonus
      "master" badge.
    - Persistence uses the Python standard library `sqlite3`, following the
      same lightweight, module-local pattern as `announcement_service.py`, so
      completions survive application restarts without a new dependency.
    - There is no server-side auth in the host app; the caller passes the
      participant name (from client-side localStorage), consistent with the
      rest of the platform.
"""

import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

NAME_MAX = 100

ITEM_TYPE_CHALLENGE = "challenge"
ITEM_TYPE_ACTIVITY = "cultural_activity"
ITEM_TYPES = [ITEM_TYPE_CHALLENGE, ITEM_TYPE_ACTIVITY]

# Storage lives inside the module's data directory, self-contained like
# announcements.db.
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_DB_PATH = os.path.join(_DATA_DIR, "explore.db")

_write_lock = threading.Lock()


# ------------------------------------------------------------------
# Errors
# ------------------------------------------------------------------

class ExploreValidationError(ValueError):
    """Raised when an Explore request fails validation."""


class ExploreNotFoundError(LookupError):
    """Raised when a referenced catalog item does not exist."""


# ------------------------------------------------------------------
# Culture guide content (Requirements F10R1, F10R2, F10R3)
# ------------------------------------------------------------------

CULTURE_FACTS = [
    {
        "title": "A Multicultural Melting Pot",
        "body": "Singapore's population blends Chinese, Malay, Indian, and Eurasian "
                "heritage. You'll see this in the four official languages (English, "
                "Mandarin, Malay, Tamil) and in neighbourhoods like Chinatown, "
                "Little India, and Kampong Glam sitting minutes apart.",
    },
    {
        "title": "Festivals All Year Round",
        "body": "Because of its multicultural mix, Singapore celebrates Chinese New "
                "Year, Hari Raya Puasa, Deepavali, and Christmas as public holidays, "
                "often with light-ups and street markets participants can visit.",
    },
    {
        "title": "A City Designed for Green Living",
        "body": "Singapore is known as a 'City in a Garden' — look out for Gardens "
                "by the Bay's Supertrees and the many park connectors linking green "
                "spaces across the island.",
    },
]

FOOD_RECOMMENDATIONS = [
    {
        "dish": "Chilli Crab",
        "description": "Singapore's unofficial national dish — mud crab in a sweet, "
                        "savoury, and mildly spicy tomato-chilli sauce. Best eaten with "
                        "fried mantou (buns) to mop up the sauce.",
        "where": "Seafood restaurants island-wide; hawker centres have lighter versions.",
    },
    {
        "dish": "Hainanese Chicken Rice",
        "description": "Poached or roasted chicken served with fragrant rice cooked "
                        "in chicken stock, chilli sauce, and ginger paste.",
        "where": "Almost every hawker centre — a great low-cost, high-reward first try.",
    },
    {
        "dish": "Laksa",
        "description": "Rice noodles in a spicy coconut curry broth with prawns, "
                        "fish cake, and bean sprouts.",
        "where": "Hawker centres; Katong is especially famous for its laksa.",
    },
    {
        "dish": "Kaya Toast + Kopi",
        "description": "Toasted bread with coconut jam and butter, served with soft-boiled "
                        "eggs and a cup of local-style coffee (kopi) — a classic breakfast.",
        "where": "Traditional coffee shops (kopitiams) and chains like Ya Kun.",
    },
]

ETIQUETTE_TIPS = [
    {
        "tip": "Tipping is not expected",
        "detail": "Most restaurants add a 10% service charge plus 9% GST to the bill; "
                  "additional tipping is uncommon and not required.",
    },
    {
        "tip": "\"Chope\" your hawker seat politely",
        "detail": "Locals reserve hawker centre seats by leaving a tissue packet or "
                  "umbrella on the table ('choping'). It's respected, but don't take "
                  "an already-choped seat.",
    },
    {
        "tip": "Remove shoes when entering a home",
        "detail": "It's customary to remove your shoes before entering someone's home, "
                  "and many temples and mosques as well.",
    },
    {
        "tip": "Littering, jaywalking, and chewing gum sale are fined",
        "detail": "Singapore enforces strict cleanliness and order laws. Use rubbish "
                  "bins, cross at marked crossings, and note that chewing gum sale "
                  "(not chewing itself) is restricted.",
    },
    {
        "tip": "Use your right hand (or both) when giving/receiving",
        "detail": "When handing something to someone, especially in Malay or Indian "
                  "cultural contexts, using the right hand (or both hands) is seen as "
                  "more respectful.",
    },
]


def get_culture_guide() -> Dict:
    """
    Return the full culture guide (facts, food recommendations, etiquette
    tips) for the Explore page and for the AI concierge's context
    (Requirements F10R1, F10R2, F10R3).
    """
    return {
        "culture_facts": list(CULTURE_FACTS),
        "food_recommendations": list(FOOD_RECOMMENDATIONS),
        "etiquette_tips": list(ETIQUETTE_TIPS),
    }


# ------------------------------------------------------------------
# Exploration challenges + cultural learning activities catalog
# (Requirements F10R4, F10R6), with badge rewards (Requirement F10R5)
# ------------------------------------------------------------------

EXPLORE_ITEMS = [
    {
        "id": "hawker-hero",
        "item_type": ITEM_TYPE_CHALLENGE,
        "title": "Hawker Hero",
        "description": "Try a dish at a hawker centre (e.g. chicken rice or laksa) and mark it done.",
        "badge_name": "Hawker Hero",
        "badge_icon": "🍜",
    },
    {
        "id": "garden-explorer",
        "item_type": ITEM_TYPE_CHALLENGE,
        "title": "Garden Explorer",
        "description": "Visit Gardens by the Bay and see the Supertrees.",
        "badge_name": "Garden Explorer",
        "badge_icon": "🌳",
    },
    {
        "id": "chinatown-wanderer",
        "item_type": ITEM_TYPE_CHALLENGE,
        "title": "Chinatown Wanderer",
        "description": "Walk through Chinatown, Little India, or Kampong Glam.",
        "badge_name": "Heritage Wanderer",
        "badge_icon": "🏮",
    },
    {
        "id": "singlish-101",
        "item_type": ITEM_TYPE_CHALLENGE,
        "title": "Singlish 101",
        "description": "Learn and try out a Singlish phrase (e.g. \"can lah\", \"shiok\") with a local.",
        "badge_name": "Local Lingo",
        "badge_icon": "🗣️",
    },
    {
        "id": "culture-facts-card",
        "item_type": ITEM_TYPE_ACTIVITY,
        "title": "Multicultural Singapore",
        "description": "Read the culture guide's facts about Singapore's four official languages and festivals.",
        "badge_name": "Culture Curious",
        "badge_icon": "📖",
    },
    {
        "id": "etiquette-quiz-card",
        "item_type": ITEM_TYPE_ACTIVITY,
        "title": "Etiquette Essentials",
        "description": "Review the etiquette guide's tips on tipping, hawker seating, and local customs.",
        "badge_name": "Etiquette Ace",
        "badge_icon": "🎌",
    },
    {
        "id": "food-tour-card",
        "item_type": ITEM_TYPE_ACTIVITY,
        "title": "Flavours of Singapore",
        "description": "Read the food guide's recommendations for must-try local dishes.",
        "badge_name": "Flavour Finder",
        "badge_icon": "🍢",
    },
]

_ITEMS_BY_ID = {item["id"]: item for item in EXPLORE_ITEMS}

# Bonus badges awarded for completing every item of a given type.
_MASTER_BADGES = {
    ITEM_TYPE_CHALLENGE: {"badge_name": "Exploration Master", "badge_icon": "🏆"},
    ITEM_TYPE_ACTIVITY: {"badge_name": "Cultural Scholar", "badge_icon": "🎓"},
}


def get_catalog() -> List[Dict]:
    """Return the static catalog of challenges and cultural learning activities."""
    return list(EXPLORE_ITEMS)


def _get_item(item_id: str) -> Dict:
    item = _ITEMS_BY_ID.get(item_id)
    if item is None:
        raise ExploreNotFoundError(f"Explore item '{item_id}' not found.")
    return item


# ------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------

def _now_iso() -> str:
    """Current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    os.makedirs(_DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they do not exist. Safe to call on every startup."""
    with _write_lock:
        conn = _connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS explore_completions (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    participant_name TEXT NOT NULL,
                    item_id          TEXT NOT NULL,
                    completed_at     TEXT NOT NULL,
                    UNIQUE(participant_name, item_id)
                );
                """
            )
            conn.commit()
        finally:
            conn.close()
    logger.info("Explore DB initialized at %s", _DB_PATH)


def _validate_name(participant_name: Optional[str]) -> str:
    name = (participant_name or "").strip()
    if not name or len(name) > NAME_MAX:
        raise ExploreValidationError("A valid participant_name is required.")
    return name


# ------------------------------------------------------------------
# Completion + progress
# ------------------------------------------------------------------

def complete_item(participant_name: str, item_id: str) -> Dict:
    """
    Mark a catalog item complete for a participant, awarding its badge.
    Idempotent: completing an already-completed item retains the original
    completion timestamp and does not error.

    Raises:
        ExploreValidationError: if participant_name is missing/invalid.
        ExploreNotFoundError: if item_id does not exist in the catalog.
    """
    name = _validate_name(participant_name)
    _get_item(item_id)  # raises if unknown

    now = _now_iso()
    with _write_lock:
        conn = _connect()
        try:
            conn.execute(
                """INSERT INTO explore_completions (participant_name, item_id, completed_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(participant_name, item_id) DO NOTHING""",
                (name, item_id, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT completed_at FROM explore_completions WHERE participant_name = ? AND item_id = ?",
                (name, item_id),
            ).fetchone()
        finally:
            conn.close()

    logger.info("Explore item '%s' completed by %s", item_id, name)
    return {"item_id": item_id, "participant_name": name, "completed_at": row["completed_at"]}


def get_progress(participant_name: str) -> Dict:
    """
    Return the full catalog annotated with this participant's completion
    status, plus the badges they've earned (one per completed item, and any
    bonus "master" badges for completing an entire category).
    """
    name = _validate_name(participant_name)

    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT item_id, completed_at FROM explore_completions WHERE participant_name = ?",
            (name,),
        ).fetchall()
    finally:
        conn.close()

    completed_map = {r["item_id"]: r["completed_at"] for r in rows}

    items = []
    for item in EXPLORE_ITEMS:
        items.append(
            {
                **item,
                "completed_at": completed_map.get(item["id"]),
            }
        )

    badges = [
        {
            "badge_name": item["badge_name"],
            "badge_icon": item["badge_icon"],
            "earned_at": completed_map[item["id"]],
            "source_item_id": item["id"],
        }
        for item in EXPLORE_ITEMS
        if item["id"] in completed_map
    ]

    for item_type, master_badge in _MASTER_BADGES.items():
        type_items = [i for i in EXPLORE_ITEMS if i["item_type"] == item_type]
        if type_items and all(i["id"] in completed_map for i in type_items):
            latest = max(completed_map[i["id"]] for i in type_items)
            badges.append(
                {
                    "badge_name": master_badge["badge_name"],
                    "badge_icon": master_badge["badge_icon"],
                    "earned_at": latest,
                    "source_item_id": None,
                }
            )

    total = len(EXPLORE_ITEMS)
    completed_count = len(completed_map)

    return {
        "participant_name": name,
        "items": items,
        "badges": badges,
        "stats": {
            "total_items": total,
            "completed_items": completed_count,
            "badge_count": len(badges),
        },
    }
