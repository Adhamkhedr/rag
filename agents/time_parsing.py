"""
Time Parsing Agent (Step 1 of the pipeline)
============================================
This is the first node in the LangGraph pipeline. Its job is to convert
the user's natural-language question into a concrete UTC time range
(start and end timestamps in ISO-8601 format).

Why this is needed:
    CloudTrail logs are stored in S3 organized by date (YYYY/MM/DD folders).
    To fetch the right log files, we need exact dates — not phrases like
    "yesterday" or "last Tuesday". This agent bridges that gap by using
    Claude to interpret the user's time references.

How it works:
    1. Gets the current UTC time (Claude doesn't know the real date on its own)
    2. Injects that time into a system prompt with rules for interpreting
       time expressions ("yesterday", "morning", "last Tuesday", etc.)
    3. Sends the user's question + system prompt to Claude via Bedrock
    4. Claude returns a JSON object like: {"start": "...", "end": "..."}
    5. The node parses that JSON and writes it to the shared LangGraph state
       as state["time_range"], which the next node (log_analysis) reads to
       know which S3 folders to scan.

Input from state:
    - state["query"] — the user's original question (e.g., "What IAM changes happened yesterday?")

Output to state:
    - state["time_range"] — dict with "start" and "end" ISO-8601 timestamps
      Example: {"start": "2026-02-06T00:00:00Z", "end": "2026-02-06T23:59:59Z"}
"""

import json
from datetime import datetime, timezone
from services.bedrock_llm import invoke_claude
from state import DocuGenState

# ---------------------------------------------------------------------------
# System prompt sent to Claude as instructions.
#
# {current_time} is a placeholder that gets replaced at runtime with the
# actual UTC time (see line in time_parsing_node). This is critical because
# Claude doesn't inherently know the current date — we must tell it.
#
# The "Rules" section ensures Claude interprets time words consistently:
#   - "yesterday" always means the full previous day (00:00 to 23:59)
#   - "last Tuesday" means the most recent Tuesday before today
#   - "morning"/"afternoon"/"evening" map to specific hour ranges
#   - If the user doesn't mention a date, assume today
#   - All times are in UTC with a Z suffix
#
# "Return ONLY valid JSON" is essential because we parse the response
# with json.loads() — any extra text (explanations, markdown) would
# cause a parsing error.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a time parsing assistant. Given a user's question about AWS events, \
extract the time range they are asking about. Return ONLY a JSON object with "start" and "end" \
fields in ISO-8601 format (UTC).

Current date and time: {current_time}

Rules:
- "yesterday" = the full day before today (00:00:00Z to 23:59:59Z)
- "last Tuesday" = the most recent Tuesday before today
- "morning" = 00:00:00Z to 12:00:00Z
- "afternoon" = 12:00:00Z to 18:00:00Z
- "evening" = 18:00:00Z to 23:59:59Z
- If no specific time is given, use the full day (00:00:00Z to 23:59:59Z)
- If no date is given, assume today
- Always use UTC (Z suffix)
- Return ONLY valid JSON. No explanation, no markdown."""


def time_parsing_node(state: DocuGenState) -> dict:
    """LangGraph node: parse time range from user query.

    This function is registered as a node in the LangGraph StateGraph
    (in graph.py). LangGraph calls it automatically and passes the
    current shared state. Whatever dict this function returns gets
    merged into that shared state.
    """
    # Step 1: Get the current UTC time as an ISO string.
    # Example: "2026-02-07T15:30:00+00:00"
    # We inject this into the prompt so Claude knows what "today" or
    # "yesterday" actually means.
    current_time = datetime.now(timezone.utc).isoformat()

    # Step 2: Plug the current time into the system prompt template,
    # replacing the {current_time} placeholder.
    prompt = SYSTEM_PROMPT.format(current_time=current_time)

    # Step 3: Call Claude via Bedrock.
    # - prompt = system-level instructions (how to interpret time)
    # - state["query"] = the user's actual question
    # - max_tokens=200 = a short limit since we only need a small JSON back
    response = invoke_claude(prompt, state["query"], max_tokens=200)

    # Step 4: Clean up Claude's response.
    # Sometimes Claude wraps its JSON in markdown code fences like:
    #   ```json
    #   {"start": "...", "end": "..."}
    #   ```
    # Even though we told it not to. This strips those fences off so
    # json.loads() can parse the raw JSON string.
    cleaned = response.strip()
    if cleaned.startswith("```"):
        # Remove the first line (```json) and the closing (```)
        cleaned = cleaned.split("\n", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0]

    # Step 5: Parse the JSON string into a Python dictionary.
    # Result example: {"start": "2026-02-06T00:00:00Z", "end": "2026-02-06T23:59:59Z"}
    time_range = json.loads(cleaned)

    # Step 6: Return the time_range dict.
    # LangGraph automatically merges this into the shared state, so after
    # this node runs, state["time_range"] will be set and available to
    # the next node in the pipeline (log_analysis).
    return {"time_range": time_range}
