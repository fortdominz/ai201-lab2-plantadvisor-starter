# Spec: Tool Functions

**File:** `tools.py`
**Status:** All three functions implemented. `get_plant_list` added as optional challenge.

---

## Purpose

These functions are the tools the agent can call. They retrieve structured data from the local plant database and seasonal data files and return it to the agent loop, which passes it to the LLM as context for generating a response.

---

## Function 1: `lookup_plant()`

### Input / Output Contract

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `plant_name` | `str` | The plant name as entered by the user or chosen by the LLM — may be any casing, common name, scientific name, or alias |

**Output:** `dict`

When the plant is **found**, return:
```python
{"found": True, "plant": <the full plant dict from _plant_db>}
```

When the plant is **not found**, return:
```python
{"found": False, "name": <normalized input>, "message": <helpful string>}
```

---

### Design Decisions

*Complete the two blank fields below before writing code. The others are pre-filled for you.*

---

#### Input normalization

Strip leading/trailing whitespace and convert to lowercase before any comparison.

```python
normalized = plant_name.strip().lower()
```

---

#### Search order

Search in this order: direct key → display name → aliases. Keys are the fastest
lookup (O(1) dict access), so check those first. Display names are the next most
likely match for clean user input. Aliases are the broadest net, so they go last.

```
1. Direct key match: normalized in _plant_db
2. Display name match: plant["display_name"].lower() == normalized
3. Alias match: normalized in [alias.lower() for alias in plant["aliases"]]
```

---

#### Alias matching approach

For each plant in the database, lowercase every alias in its aliases list and check if the normalized input matches any of them:

```
for each plant in _plant_db:
    if normalized in [alias.lower() for alias in plant["aliases"]]:
        return found result
```

This is O(n * m) where n is the number of plants and m is the average alias count — acceptable for a small local database. For a database of thousands of plants, a pre-built reverse lookup dict (alias → key) at module load time would reduce this to O(1) per query.

---

#### Not-found message

When a plant isn't found, the message tells the LLM exactly what it can and can't do — so it doesn't invent specific care data:

```
f"'{plant_name}' is not in my plant database. My database includes: {list of display_names}. 
Do not invent specific care instructions for this plant. Instead, acknowledge it's not in 
your database and offer general guidance based on the plant type the user describes 
(e.g., tropical, succulent, fern) without presenting it as specific data."
```

---

#### Implementation Notes

*Fill this in after implementing and running the app.*

**Test: does `"devil's ivy"` return the pothos entry?**
```
yes — matched via alias list on the pothos entry
```

**Test: does `"SNAKE PLANT"` return the snake plant entry?**
```
yes — input normalized to "snake_plant" matched the direct key
```

**One edge case you discovered while implementing:**
```
Display name matching requires .lower() comparison since display_names are title-cased 
(e.g., "Pothos") but normalized input is lowercase. Without .lower() on display_name, 
a user typing "pothos" would miss the display name match and fall through to alias search.
```

---

## Function 2: `get_seasonal_conditions()`

### Input / Output Contract

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `season` | `str \| None` | One of `"spring"`, `"summer"`, `"fall"`, `"winter"`, or `None` to auto-detect |

**Output:** `dict`

The full season dict from `_season_data`, plus one additional field:

| Added field | Type | Value |
|-------------|------|-------|
| `"detected_season"` | `bool` | `True` if auto-detected from the month; `False` if season was passed as an argument |

---

### Design Decisions

*This function is pre-implemented — read through these fields and the code before working on `lookup_plant`.*

---

#### Auto-detection logic

When `season` is `None`, get the current calendar month with `datetime.now().month`
and look it up in the `_MONTH_TO_SEASON` dict, which maps month numbers to season strings.

```python
current_month = datetime.now().month
season_key = _MONTH_TO_SEASON[current_month]
```

---

#### Season validation

If the caller passes an invalid season string (e.g., `"monsoon"`), the function
falls back to auto-detection — same as if `None` were passed. The `VALID_SEASONS`
set acts as the gate:

```python
VALID_SEASONS = {"spring", "summer", "fall", "winter"}
if season and season.lower() in VALID_SEASONS:
    ...  # use provided season
else:
    ...  # auto-detect
```

---

#### Return structure

The full season dict from `_season_data`, plus a `detected_season` boolean. Example for spring:

```python
{
    "season": "spring",
    "watering": "Increase watering frequency as plants break dormancy ...",
    "fertilizing": "Resume feeding with a balanced fertilizer ...",
    "light": "Days are lengthening — move plants closer to windows ...",
    "pests": "Watch for spider mites and aphids as temperatures rise ...",
    "detected_season": True   # True = auto-detected; False = caller specified
}
```

---

#### Implementation Notes

*Fill this in after testing.*

**Test: does calling with `season=None` return the correct season for the current month?**
```
Current month: June (6)
Expected season: Summer
Returned season: Summer (name field) | detected_season: True ✓
```

**Test: does calling with `season="winter"` return winter data regardless of the current month?**
```
yes — returns name: "Winter" with detected_season: False, confirming the
caller-specified branch is taken and auto-detection is skipped.
```

---

## Function 3: `get_plant_list()` — Optional Challenge

### Input / Output Contract

**Inputs:** None

**Output:** `dict`

```python
{
    "total": 15,
    "plants": [{"name": "Pothos", "difficulty": "easy"}, ...],
    "by_difficulty": {
        "easy": ["Pothos", "Snake Plant", ...],
        "moderate": ["Monstera", "Rubber Plant", ...],
        "hard": ["Fiddle Leaf Fig", "Calathea"]
    }
}
```

### Design Decisions

**Why group by difficulty?** Questions like "what's a good beginner plant?" require the LLM
to filter by difficulty. Returning a flat list forces the LLM to scan every entry; grouping
by difficulty gives it the relevant subset directly.

**No input parameters.** The function always returns the full database — the LLM decides
what subset to surface in its response. This keeps the tool simple and avoids a search
API design that would duplicate `lookup_plant`'s responsibility.

### Implementation Notes

**Test: does `"what plants are good for beginners?"` trigger this tool?**
```
yes — the LLM calls get_plant_list() and surfaces the easy-difficulty entries.
```

**Test: does `"what plants do you know about?"` trigger this tool?**
```
No — this is a documented limitation. The model answers this meta-question from
its training data rather than calling get_plant_list, because it has strong priors
about common houseplants. The tool fires reliably for difficulty-based questions
("good beginner plant") where the model needs structured data it doesn't have.
The plant list was injected into the system prompt as a fallback so the model can
at least read the correct names from context.

Key insight: tool descriptions control *which* tool gets called, not *whether* the
model decides it needs a tool at all. This maps to Discussion Prompt #1.
```
