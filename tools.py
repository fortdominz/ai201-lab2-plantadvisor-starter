import json
import os
from datetime import datetime
from config import DATA_PATH

# Plant database and seasonal data are loaded once at module load.
# This mirrors how a real service would cache its data source in memory.
with open(os.path.join(DATA_PATH, "plants.json"), encoding="utf-8") as f:
    _plant_db = json.load(f)

with open(os.path.join(DATA_PATH, "seasons.json"), encoding="utf-8") as f:
    _season_data = json.load(f)

# Maps calendar months to seasons for auto-detection.
_MONTH_TO_SEASON = {
    12: "winter", 1: "winter", 2: "winter",
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "fall",  10: "fall",  11: "fall",
}


def lookup_plant(plant_name: str) -> dict:
    """
    Search the plant database for a plant by name and return its care information.

    Searches in order:
      1. Direct key match  (e.g., "pothos"       → _plant_db["pothos"])
      2. Display name match (e.g., "Pothos"       → plant["display_name"].lower())
      3. Alias match        (e.g., "devil's ivy"  → plant["aliases"])

    All matching is case-insensitive with whitespace stripped.
    """
    normalized = plant_name.strip().lower()

    # 1. Direct key match
    if normalized in _plant_db:
        return {"found": True, "plant": _plant_db[normalized]}

    # 2. Display name + 3. Alias match
    for plant in _plant_db.values():
        if plant["display_name"].lower() == normalized:
            return {"found": True, "plant": plant}
        if normalized in [alias.lower() for alias in plant["aliases"]]:
            return {"found": True, "plant": plant}

    # Not found — give the LLM a message that prevents hallucination
    known_plants = ", ".join(p["display_name"] for p in _plant_db.values())
    return {
        "found": False,
        "name": normalized,
        "message": (
            f"'{plant_name}' is not in my plant database. "
            f"Plants I have specific data for: {known_plants}. "
            "Do not invent specific care instructions for this plant. "
            "Acknowledge it is not in your database, then offer general guidance "
            "based on what the user describes about it (e.g., succulent, tropical, fern) "
            "without presenting that guidance as specific data."
        ),
    }


def get_plant_list() -> dict:
    """
    Return all plants in the database with their display name and difficulty level.

    Use this when the user asks which plants the advisor knows about, or asks for
    recommendations by difficulty (e.g., 'easy plants', 'beginner plant').
    """
    plants = [
        {"name": p["display_name"], "difficulty": p["difficulty"]}
        for p in _plant_db.values()
    ]
    by_difficulty = {"easy": [], "moderate": [], "hard": []}
    for p in plants:
        by_difficulty[p["difficulty"]].append(p["name"])
    return {"total": len(plants), "plants": plants, "by_difficulty": by_difficulty}


def get_seasonal_conditions(season: str | None = None) -> dict:
    """
    Return current seasonal care context for houseplants.

    If season is provided and valid, returns that season's data.
    If season is None (or invalid), auto-detects from the current calendar month.

    Pre-implemented — read through this and the spec before working on lookup_plant().
    """
    VALID_SEASONS = {"spring", "summer", "fall", "winter"}

    if season and season.lower() in VALID_SEASONS:
        # Caller specified a valid season — use it directly
        season_key = season.lower()
        detected = False
    else:
        # Auto-detect from the current month using the _MONTH_TO_SEASON mapping
        current_month = datetime.now().month
        season_key = _MONTH_TO_SEASON[current_month]
        detected = True

    # Copy the season dict so we don't mutate the cached data
    result = dict(_season_data[season_key])
    result["detected_season"] = detected
    return result
