"""
Explore / Cultural Experience Service

Provides culture guide content, exploration challenges, cultural activities,
and a badge/achievement system for participants.
Uses SQLite for progress persistence.
"""

import logging
import os
import sqlite3
import threading
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

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
