import json
from groq import Groq
from config import GROQ_API_KEY, LLM_MODEL, MAX_TOOL_ROUNDS
from tools import lookup_plant, get_seasonal_conditions, get_plant_list

_client = Groq(api_key=GROQ_API_KEY)

# ──────────────────────────────────────────────
# Plant context — injected into system prompt at startup
#
# The plant list is static database metadata, not dynamic runtime data.
# Injecting it directly into the context is more reliable than asking the
# LLM to call a tool for a question it thinks it already knows the answer to
# from training data. The get_plant_list tool still serves for difficulty-based
# recommendation queries where the LLM needs to reason over the full list.
# ──────────────────────────────────────────────

_plant_data = get_plant_list()
_PLANT_CONTEXT = (
    f"Plants in your database ({_plant_data['total']} total):\n"
    f"  Easy care:     {', '.join(_plant_data['by_difficulty']['easy'])}\n"
    f"  Moderate care: {', '.join(_plant_data['by_difficulty']['moderate'])}\n"
    f"  Hard care:     {', '.join(_plant_data['by_difficulty']['hard'])}\n"
)

# ──────────────────────────────────────────────
# Tool definitions
#
# These are the schemas that tell the LLM what tools are available and how to
# call them. The LLM reads these descriptions and decides when (and how) to use
# each tool. They're already complete — your job is to implement the tool
# functions in tools.py and the agent loop below.
# ──────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_plant",
            "description": (
                "Look up care information for a specific houseplant by name. "
                "Returns detailed watering, light, humidity, and temperature requirements. "
                "Use this whenever the user asks about a specific plant."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plant_name": {
                        "type": "string",
                        "description": "The plant name to look up. Can be a common name, scientific name, or nickname (e.g., 'pothos', 'devil's ivy', 'Monstera deliciosa').",
                    }
                },
                "required": ["plant_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_plant_list",
            "description": (
                "Return the full list of houseplants in this database, grouped by care difficulty. "
                "Use this tool whenever the user asks: which plants are in your database, "
                "what plants do you know about, what plants can you help with, "
                "what's a good beginner or easy plant, what plants are hard to care for, "
                "or any question that requires knowing the complete set of plants available. "
                "Do NOT answer questions about database contents from general knowledge — "
                "always call this tool first."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_seasonal_conditions",
            "description": (
                "Get seasonal care adjustments for houseplants. "
                "Returns guidance on watering, fertilizing, light, and pests for the current or specified season. "
                "Use this when a user asks a season-specific question, or to complement plant care advice with seasonal context."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "season": {
                        "type": "string",
                        "description": "The season to get care conditions for. If omitted, the current season is detected automatically.",
                        "enum": ["spring", "summer", "fall", "winter"],
                    }
                },
                "required": [],
            },
        },
    },
]

# ──────────────────────────────────────────────
# System prompt
# ──────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are a knowledgeable and friendly plant care advisor. "
    "Help users care for their houseplants by looking up specific plant information "
    "and current seasonal conditions using your available tools.\n\n"
    f"{_PLANT_CONTEXT}\n"
    "Use lookup_plant whenever a user asks about a specific plant by name. "
    "Use get_seasonal_conditions when a question involves a specific season or time of year. "
    "Use get_plant_list when a user asks for plant recommendations by difficulty.\n\n"
    "When lookup_plant returns found: False, tell the user the plant is not in your database "
    "and offer general guidance based on what they describe — do not invent specific care data.\n\n"
    "Keep your advice practical. Cite your source when you have data "
    "(e.g., 'According to the care data for your monstera...')."
)

# ──────────────────────────────────────────────
# Tool dispatch
#
# This is already complete. It routes tool calls from the LLM to the actual
# Python functions in tools.py, and returns results as JSON strings (which is
# what the Groq API expects for tool results).
# ──────────────────────────────────────────────

def dispatch_tool(tool_name: str, tool_args: dict) -> str:
    """Route a tool call to the correct function and return the result as a JSON string."""
    print(f"  → Tool call: {tool_name}({tool_args})")
    if tool_name == "lookup_plant":
        result = lookup_plant(tool_args["plant_name"])
    elif tool_name == "get_plant_list":
        result = get_plant_list()
    elif tool_name == "get_seasonal_conditions":
        result = get_seasonal_conditions(tool_args.get("season"))
    else:
        result = {"error": f"Unknown tool: {tool_name}"}
    print(f"  ← Result: {json.dumps(result)[:120]}{'...' if len(json.dumps(result)) > 120 else ''}")
    return json.dumps(result)


# ──────────────────────────────────────────────
# Agent loop
# ──────────────────────────────────────────────

def run_agent(user_message: str, history: list) -> str:
    """
    Run the plant care agent for one user turn and return its response.

    Builds a messages list, calls the LLM with tool definitions, and loops
    until the LLM produces a final text response or MAX_TOOL_ROUNDS is reached.
    """
    # 1. Build messages: system prompt + history + new user message
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    for user_msg, assistant_msg in history:
        messages.append({"role": "user", "content": user_msg})
        if assistant_msg:
            messages.append({"role": "assistant", "content": assistant_msg})

    messages.append({"role": "user", "content": user_message})

    # 2. Agent loop — runs until LLM stops calling tools or MAX_TOOL_ROUNDS hit
    for _ in range(MAX_TOOL_ROUNDS):
        response = _client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
        )

        assistant_message = response.choices[0].message

        # No tool calls — LLM has a final answer
        if not assistant_message.tool_calls:
            return assistant_message.content or "I wasn't able to generate a response. Please try again."

        # Append assistant message BEFORE tool results (API requires this order)
        messages.append(assistant_message)

        # Execute each tool call and append results
        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)
            tool_result = dispatch_tool(tool_name, tool_args)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            })

    # MAX_TOOL_ROUNDS reached — force a final text response with no more tools
    response = _client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        tools=TOOL_DEFINITIONS,
        tool_choice="none",
    )
    return response.choices[0].message.content or "I reached my reasoning limit. Please try a simpler question."
