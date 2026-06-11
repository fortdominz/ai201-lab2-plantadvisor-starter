# Lab Reflection — Plant Advisor (Tinker 2)

**Lab type:** Tool-calling agent
**Stack:** Python, Groq (llama-3.3-70b-versatile), Gradio, python-dotenv
**Repo:** https://github.com/fortdominz/ai201-lab2-plantadvisor-starter
**Completed:** June 2026
**Built by:** Dominion Eze

---

## Overview

Plant Advisor is a conversational agent that helps users care for their houseplants. Unlike a chatbot that just passes questions to an LLM and returns whatever it says, this agent has tools it can call: a plant care database lookup (`lookup_plant`), a seasonal conditions checker (`get_seasonal_conditions`), and a plant list by difficulty (`get_plant_list`). The LLM decides — based on the user's question — which tools to call, in what order, and when it has enough to give a final answer. The lab covered implementing the tools, building the agent loop that drives them, and designing a graceful fallback for when a user asks about a plant that isn't in the database.

---

## What Was Built

**Milestone 1 — Tool functions (`tools.py`):**
- `lookup_plant(plant_name)` — searches a 15-plant JSON database by key, display name, and alias list. Case-insensitive, whitespace-stripped. Returns `{"found": True, "plant": {...}}` on match or `{"found": False, "message": "..."}` with a not-found message that tells the LLM not to invent specific care data.
- `get_seasonal_conditions(season=None)` — returns care guidance for the current season (auto-detected from the calendar month) or a specified season. Always returns valid data because seasons are a closed set of four values.
- `get_plant_list()` — added as optional challenge. Returns all 15 plants grouped by care difficulty (easy/moderate/hard). Useful for questions like "what's a good beginner plant?"

**Milestone 2 — Agent loop (`agent.py`):**
- `run_agent(user_message, history)` — builds the messages list (system prompt + conversation history + new message), calls the Groq API with tool definitions attached, and loops: if the response contains `tool_calls`, execute each tool, append the assistant message and all tool results to the messages list, and call the API again. If the response contains `content` instead, return it as the final answer. If `MAX_TOOL_ROUNDS` is reached without a text response, force one final call with `tool_choice="none"`.

**Milestone 3 — Graceful degradation (system prompt + not-found message):**
- Updated the not-found message in `lookup_plant` to explicitly tell the LLM not to invent care instructions and to offer general guidance instead.
- Updated the system prompt to state: "When lookup_plant returns found: False, tell the user the plant is not in your database and offer general guidance based on what they describe — do not invent specific care data."

**Optional challenge additions:**
- `get_plant_list()` tool registered in `TOOL_DEFINITIONS` and `dispatch_tool()`
- Plant list injected into the system prompt at module load time as static context (see architectural decision below)
- All spec Implementation Notes completed for both tool functions and the agent loop

---

## Key Learnings

### Agents vs. Chatbots

A chatbot takes a message, calls an LLM, returns the response. That's one function call. An agent has tools, and the LLM decides dynamically whether to call one, two, or none of them based on the question. "How often should I water my monstera in winter?" needs two tools — plant lookup gives the care requirements, seasonal check gives the winter context. "What's a tropical plant good for beginners?" needs the plant list. "Hello, what can you do?" needs no tools at all. The LLM makes that call. Your job as the implementer is to give it accurate tool descriptions and a loop that handles however many calls it decides to make.

### The messages list is the backbone of every agent turn

The API doesn't maintain state. Every tool-calling round works by growing the messages list: system prompt, conversation history, user message, then for each LLM response — if it called tools — append the full assistant message (with its `tool_calls`) and then append one tool result message per call. The ordering constraint is strict: assistant message must come before the tool results because each tool result contains a `tool_call_id` that references the assistant message that requested it. If you append the result before the request, the API can't match them and returns an error.

### Tool descriptions control which tool fires — not whether the model decides a tool is needed

The most surprising thing in this lab: tool descriptions tell the LLM what each tool does and when to use it, but they don't override the model's internal judgment about whether it needs a tool at all. For questions the model feels confident answering from training data, it skips tools entirely. This came up sharply with `get_plant_list` — the question "What plants are good for beginners?" reliably triggered the tool, but "What plants do you know about?" did not. The model treats the second question as something it already knows (common houseplants) and answers from training data. No tool description or system prompt rule consistently fixed this. See the Honest Failure Case section below.

### More system prompt rules does not mean more reliable behavior

After observing `get_plant_list` not firing for "What plants do you know about?", I tried progressively stronger system prompt rules — adding "RULE: you MUST call get_plant_list()" and similar directives. Each iteration either didn't help or made things worse. The most aggressive version caused the model to start leaking raw function-call syntax (`<function=lookup_plant>{"plant_name": "snake plant"}</function>`) as plain text in its response — the model was so confused by competing directives that it produced malformed output. The lesson: agent system prompts should be short, positive, and specific ("use X when Y") — not a list of prohibitions and requirements. Every rule added competes for the model's attention.

### Static configuration belongs in context, not behind a tool

The fix for "What plants do you know about?" was architectural: inject the plant list directly into the system prompt at startup. The plant database doesn't change at runtime — it's loaded once from `plants.json`. That makes it configuration, not dynamic data. Putting it in context means the model can always read the exact list, regardless of whether it decides to call a tool. The `get_plant_list` tool still serves for difficulty-based recommendation questions where the model benefits from the structured `by_difficulty` grouping. But simple listing questions are answered from context. The rule: if the data is static and small enough, it belongs in context. If it's dynamic, user-specific, or too large for the context window, it belongs behind a tool.

---

## Architectural Decisions

**Character-based tool dispatch over a framework**
Rather than using LangChain or a similar agent framework, the loop is implemented from scratch: build messages, call API, check for `tool_calls`, execute with `dispatch_tool()`, append results, repeat. Building it manually meant seeing exactly what the framework hides — specifically the messages list structure and the ordering requirement for assistant messages before tool results. That understanding is what makes it possible to debug agent behavior rather than just use it as a black box.

**`found: False` return value over raising an exception**
`lookup_plant` returns a structured `{"found": False, "message": "..."}` dict rather than raising an error when a plant isn't in the database. An exception would halt the agent loop and return nothing useful to the user. The `found: False` result keeps the loop running — the LLM reads the message, acknowledges the gap, and offers general guidance. The message field is what shapes that guidance: it explicitly lists what plants are in the database and instructs the LLM not to invent specific care data.

**Seasonal data always returns rather than erroring on bad input**
`get_seasonal_conditions` falls back to auto-detection for any invalid season string rather than returning an error. This matches how the tool is used: if the LLM passes `"monsoon"` or an empty string, auto-detecting the current season is always the right fallback. An error would leave the agent with no seasonal context at all.

**Plant list injected into the system prompt at module load**
See Key Learnings above. The choice was: fight the model's priors with progressively stronger tool description rules, or work with the model's behavior by putting the information where it naturally looks — the system prompt. The second approach is faster, more reliable, and architecturally correct for static data.

---

## AI Collaboration

### Instance that worked well: spec-driven tool implementation

For `lookup_plant`, I gave the spec fields (alias matching approach, search order, not-found message design) to Claude before writing any code. The generated implementation matched the spec exactly — the three-step search order (key → display name → alias), the normalized input variable, and the not-found message format. What made it work was writing the spec decisions first. "Find plants in the database and return care info" would have produced generic code. "Search in order: direct key match, then display name lowercase comparison, then alias list comprehension" produced the specific implementation I wanted.

### Instance where AI fell short: system prompt rule escalation

Over four iterations trying to get `get_plant_list` to fire for "What plants do you know about?", Claude (me, in this context) kept escalating the system prompt rules — adding RULE: directives, then stronger language, then both system prompt and tool description changes. Each iteration compounded the confusion until the model broke and started outputting function-call syntax as text. The better move would have been to recognize earlier that LLM behavior for a specific question type isn't reliably changeable through prompt rules alone — and to reach for the architectural solution (inject the plant list into context) after the first or second failed attempt instead of the fourth.

---

## Discussion Prompt Answers

**1. Did the agent consistently call `get_seasonal_conditions` for season-specific questions, or sometimes skip it?**

For explicit season questions ("in winter", "this time of year"), it fired consistently. For general care questions, sometimes both tools fired and sometimes only `lookup_plant` did — the plant data already includes brief seasonal notes in its structure, so the LLM sometimes decided it had enough without calling the seasonal tool. This shows that tool descriptions control which tool fires when the model decides a tool is needed, but they don't control whether the model judges a tool necessary in the first place. To make it more predictable: explicitly state in the system prompt "always call get_seasonal_conditions to complement plant care advice."

**2. How would you add the ability to query plants by attribute (e.g., "good for low light")?**

Add a `search_plants_by_attribute(attribute, value)` tool that iterates the plant database and returns plants matching a given attribute-value pair. Example: `search_plants_by_attribute("light", "low")` would return plants whose light requirement description contains "low." Alternatively, add pre-built attribute lists to `plants.json` (e.g., `"tags": ["low-light", "pet-safe"]`) and filter by tag. The tool description would need to enumerate the supported attributes clearly — "attribute must be one of: light, watering, difficulty, pet-safe" — otherwise the LLM might call it with arbitrary attributes the function can't handle.

**3. What would cause the agent loop to run forever? How does `MAX_TOOL_ROUNDS` help?**

The loop runs until the LLM stops requesting tools. An infinite loop would happen if a tool always returns empty or error results and the LLM keeps retrying rather than accepting that it can't get the data. `MAX_TOOL_ROUNDS` caps the iteration count. When it's reached, the code makes one final API call with `tool_choice="none"` to force a text response — this gives the user something meaningful ("I reached my reasoning limit") rather than an empty string or crash.

**4. Why did the LLM call `get_seasonal_conditions()` after a successful `lookup_plant` result?**

The LLM determined from the user's question (or the tool description's "use this to complement plant care advice") that seasonal context would make the answer more complete. `lookup_plant` returning `found: True` doesn't signal that the conversation is done — it signals that one piece of context is ready. The LLM still has to decide whether that's enough to answer the question or whether more context would help. For a question like "how often should I water my monstera this time of year?", the seasonal check adds information the plant lookup alone doesn't give. The LLM makes that call autonomously.

---

## Honest Failure Case

**"What plants do you know about?" does not reliably trigger `get_plant_list`.**

The model (llama-3.3-70b-versatile) consistently answered this question from training data — listing a few common houseplants as examples rather than enumerating the database. It tried four different approaches to fix this: stronger tool description, system prompt RULE directives, combined changes, and more aggressive language. None worked reliably. The fourth attempt caused the model to output raw function-call syntax as plain text, a signal that the prompt had become too contradictory to follow.

Root cause: the model was trained to be conversationally helpful for meta-questions about its own capabilities. "What plants do you know about?" matches that training pattern. The model answers it from its weights, not from a tool, because it has strong priors about common houseplants and doesn't recognize that the database (not its training data) is the authoritative source.

Fix that worked: inject the plant list into the system prompt as static context at startup. The model reads the list directly from context and can answer listing questions accurately. The `get_plant_list` tool still fires for difficulty-based questions where the structured data is useful.

Takeaway: **LLM priors beat tool description rules for questions the model thinks it already knows.** The right solution is architectural (put the data in context), not prompt-based (add more rules).

---

## Wins

- Agent loop working end-to-end — tool calls visible in terminal, grounded responses in UI
- `"devil's ivy"` correctly matched to Pothos via alias ✅
- `"SNAKE PLANT"` correctly matched via normalized key ✅
- "Bird of paradise" graceful degradation: acknowledged not in database, offered general tropical guidance, no invented specifics ✅
- "What plants are good for beginners?" correctly triggers `get_plant_list`, surfaces easy-care plants ✅
- All spec Implementation Notes completed — both tool functions and agent loop ✅
- `MAX_TOOL_ROUNDS` safeguard implemented and tested ✅

## Hiccups

- Gradio 6.x changed history format from `[user, assistant]` tuples to `{"role": ..., "content": ...}` dicts — `app.py` was written for the old format. Fixed by adding a history conversion step in `chat()`.
- System prompt escalation caused model to output raw function-call syntax as text — needed to dial back to a simple, positive prompt
- `get_plant_list` does not reliably fire for "What plants do you know about?" despite multiple prompt attempts — solved architecturally (plant list injected into system prompt)
- Seasonal data keys include `name` not `season` — caught when a checkpoint test tried `r4['season']` and got a KeyError. Fixed by checking the actual keys before printing.

---

## What I'd Tell My Past Self Before Starting

Read the full agent loop cycle before writing a single line of `run_agent`. The only thing that matters is understanding the messages list: system prompt → history → user message → assistant message (with tool calls) → tool result messages → repeat. Once that structure is clear in your head, the implementation is 20 lines. Going in without that mental model means you'll write the loop in the wrong order and spend an hour debugging API message ordering errors.

---

## What This Project Taught Me That a Tutorial Never Would

Every tutorial shows a clean agent demo where the LLM always picks the right tool. What they don't show you is what happens when the LLM's training data is a stronger signal than your tool description. "What plants do you know about?" should call `get_plant_list`. It doesn't, because the model has billions of houseplant training tokens and thinks it already knows the answer. Understanding agents means understanding that tool selection is probabilistic — you're betting that your description is a stronger signal than whatever the model learned in pretraining. When it isn't, no prompt rule fixes it. The right move is to recognize the category of problem (static data that belongs in context) and use the architectural solution instead of fighting the model.

---

## Portfolio Signal

- **Skills demonstrated:** Tool-calling agent loop implementation, function calling API, graceful degradation design, system prompt engineering, Gradio 6.x integration, structured tool return design
- **Problem-solving shown:** Identified and documented the exact failure mode when model priors override tool descriptions; reached an architectural solution (context injection) after exhausting prompt-based approaches; implemented and spec'd an optional third tool
- **What I'd say in an interview:** "I built a tool-calling agent for plant care advice. The interesting part was debugging why the LLM wouldn't call my `get_plant_list` tool for a question it was specifically designed to answer. After four failed prompt approaches — the fourth one broke the model into outputting raw function-call syntax — I realized the problem wasn't the prompt, it was the architecture. The plant list is static data, so it belongs in the system prompt context, not behind a tool the model has to choose to call. That shift fixed it immediately."
- **The one thing that makes this stand out:** Documenting the `get_plant_list` failure case honestly — including the four failed approaches and what each one revealed — rather than presenting a version that only shows the parts that worked.
