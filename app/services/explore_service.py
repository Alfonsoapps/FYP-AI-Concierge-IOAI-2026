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
Explore / Cultural Experience Service

Provides culture guide content, exploration challenges, cultural activities,
and a badge/achievement system for participants.
Uses SQLite for progress persistence.
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


_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_DB_PATH = os.path.join(_DATA_DIR, "explore.db")
_LOCK = threading.Lock()

# ------------------------------------------------------------------
# Static content
# ------------------------------------------------------------------

CULTURE_FACTS = [
    {"id": "fact-1", "title": "Multicultural Melting Pot", "content": "Singapore is home to Chinese, Malay, Indian, and Eurasian communities living harmoniously. Each culture contributes its own festivals, food, and traditions, making Singapore one of the most diverse nations in the world."},
    {"id": "fact-2", "title": "Garden City", "content": "Singapore is known as the 'Garden City' with over 300 parks and 4 nature reserves. The government mandates that trees be planted along every road, and buildings often incorporate vertical gardens."},
    {"id": "fact-3", "title": "Four Official Languages", "content": "English, Mandarin, Malay, and Tamil are all official languages. English is the language of business and education. 'Singlish' — a creole mixing all four — is spoken informally."},
]

FOOD_RECOMMENDATIONS = [
    {"id": "food-1", "name": "Hainanese Chicken Rice", "description": "Singapore's national dish — poached chicken with fragrant rice, chili sauce, and ginger paste. Try it at Maxwell Food Centre (SGD 4-5).", "location": "Maxwell Food Centre"},
    {"id": "food-2", "name": "Laksa", "description": "Spicy coconut curry noodle soup with prawns, fishcake, and bean sprouts. Rich, aromatic, and unforgettable.", "location": "328 Katong Laksa"},
    {"id": "food-3", "name": "Char Kway Teow", "description": "Stir-fried flat rice noodles with soy sauce, prawns, Chinese sausage, and bean sprouts. Smoky and addictive.", "location": "Chinatown Complex"},
    {"id": "food-4", "name": "Roti Prata", "description": "Flaky Indian flatbread served with curry dipping sauce. Best enjoyed for breakfast or supper.", "location": "Mr and Mrs Mohgan's, Joo Chiat"},
]

ETIQUETTE_TIPS = [
    {"id": "tip-1", "title": "Remove Shoes", "content": "Always remove your shoes before entering someone's home. Many temples and mosques also require shoes off."},
    {"id": "tip-2", "title": "No Gum", "content": "Chewing gum is restricted in Singapore. You won't find it in shops. Bringing gum for personal use is technically allowed but spitting it out is a fine."},
    {"id": "tip-3", "title": "Tipping Not Expected", "content": "Tipping is not customary. Most restaurants include a 10% service charge. Taxi drivers don't expect tips."},
    {"id": "tip-4", "title": "Keep It Clean", "content": "Littering carries fines of SGD 300+. Eating/drinking is banned on MRT trains (SGD 500 fine). Singapore takes cleanliness seriously."},
    {"id": "tip-5", "title": "Queue Culture", "content": "Singaporeans love queuing. Cutting in line is considered very rude. The longer the queue at a food stall, the better the food."},
]

CHALLENGES = [
    {"id": "challenge-hawker", "title": "Hawker Hero", "description": "Visit a hawker centre and try 3 different local dishes. Take a photo of each!", "badge": "🍜 Hawker Hero", "points": 30},
    {"id": "challenge-garden", "title": "Garden Explorer", "description": "Visit Gardens by the Bay and find the Supertree Grove. Walk the OCBC Skyway if you dare!", "badge": "🌿 Garden Explorer", "points": 25},
    {"id": "challenge-chinatown", "title": "Chinatown Wanderer", "description": "Explore Chinatown — find the Buddha Tooth Relic Temple, try a traditional Chinese dessert, and buy a souvenir.", "badge": "🏮 Chinatown Wanderer", "points": 25},
    {"id": "challenge-singlish", "title": "Singlish 101", "description": "Learn 5 Singlish phrases and use them in conversation. Lah, lor, leh, can, shiok!", "badge": "🗣️ Singlish 101", "points": 20},
]

ACTIVITIES = [
    {"id": "activity-multicultural", "title": "Multicultural Singapore", "description": "Learn about Singapore's 4 major ethnic communities and their contributions to the nation.", "type": "learning", "items": ["Chinese Heritage Centre", "Malay Heritage Centre", "Indian Heritage Centre", "Peranakan Museum"]},
    {"id": "activity-etiquette", "title": "Etiquette Essentials", "description": "Master the do's and don'ts of Singapore culture before exploring the city.", "type": "learning", "items": ["Greeting customs", "Dining etiquette", "Temple/mosque etiquette", "Public behaviour norms"]},
    {"id": "activity-flavours", "title": "Flavours of Singapore", "description": "A guided food journey through Singapore's diverse culinary traditions.", "type": "food_tour", "items": ["Chinese: Dim Sum", "Malay: Nasi Lemak", "Indian: Biryani", "Peranakan: Nyonya Kueh"]},
]

ALL_ITEMS = {c["id"]: c for c in CHALLENGES + ACTIVITIES}
BONUS_BADGE = {"id": "bonus-master", "title": "🏆 Exploration Master", "description": "Completed all exploration challenges and activities!"}

# ------------------------------------------------------------------
# Database
# ------------------------------------------------------------------

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
    """Create the explore progress table."""
    with _LOCK, _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS explore_progress (
                participant_name TEXT NOT NULL,
                item_id TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                PRIMARY KEY (participant_name, item_id)
            )
        """)
    logger.info("Explore DB initialized at %s", _DB_PATH)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def get_culture_guide() -> Dict:
    """Return the full culture guide content."""
    return {
        "facts": CULTURE_FACTS,
        "food_recommendations": FOOD_RECOMMENDATIONS,
        "etiquette_tips": ETIQUETTE_TIPS,
    }


def get_catalog() -> Dict:
    """Return all challenges and activities."""
    return {
        "challenges": CHALLENGES,
        "activities": ACTIVITIES,
    }


def get_progress(participant_name: str) -> Dict:
    """Return a participant's exploration progress and earned badges."""
    name = (participant_name or "").strip()
    if not name:
        return {"completed": [], "badges": [], "total_points": 0}

    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT item_id, completed_at FROM explore_progress WHERE participant_name = ?",
            (name,),
        ).fetchall()

    completed_ids = [row["item_id"] for row in rows]
    badges = []
    total_points = 0

    for item_id in completed_ids:
        item = ALL_ITEMS.get(item_id)
        if item and "badge" in item:
            badges.append({"id": item_id, "badge": item["badge"], "title": item["title"]})
        if item and "points" in item:
            total_points += item["points"]

    # Check for bonus badge (all challenges + activities completed)
    all_ids = set(ALL_ITEMS.keys())
    if all_ids and all_ids.issubset(set(completed_ids)):
        badges.append({"id": BONUS_BADGE["id"], "badge": BONUS_BADGE["title"], "title": BONUS_BADGE["description"]})

    return {
        "completed": [{"item_id": r["item_id"], "completed_at": r["completed_at"]} for r in rows],
        "badges": badges,
        "total_points": total_points,
    }


def complete_item(participant_name: str, item_id: str) -> Dict:
    """Mark an item as completed for a participant."""
    name = (participant_name or "").strip()
    if not name:
        raise ValueError("participant_name is required.")
    if item_id not in ALL_ITEMS:
        raise ValueError(f"Unknown item: {item_id}")

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO explore_progress (participant_name, item_id, completed_at) VALUES (?, ?, ?)",
            (name, item_id, now),
        )

    logger.info("Explore item completed: %s -> %s", name, item_id)
    return get_progress(name)
