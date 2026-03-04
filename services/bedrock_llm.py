"""
It's the Claude wrapper. Every time any agent in the pipeline needs to generate text, it     calls invoke_claude() from this file.                                                      
                                                                                             
  Four places use it:                                                                                                                                                                     
  1. Time Parsing — "The user said 'yesterday'. What's that in ISO-8601?" → Claude returns     {"start": "2026-02-06T00:00:00Z", "end": "2026-02-06T23:59:59Z"}                           
  2. Log Analysis — "Here are 20 CloudTrail events. Summarize them in 2-3 sentences." →      
  Claude returns a summary paragraph
  3. Event Filter — "The user asked about security groups. Which categories are relevant:
  IAM_CHANGE, SECURITY_GROUP, S3_CONFIG?" → Claude returns "SECURITY_GROUP"
  4. Report Synthesis — "Here are the events and relevant AWS docs. Write an audit report." →
   Claude returns the full Markdown report

  The function itself is simple — it takes two strings (system prompt + user message), sends 
  them to Claude via Bedrock, and returns Claude's text response. The bedrock_embeddings.py  
  file does a similar thing but for a different purpose — it sends text to Titan and gets    
  numbers back. This file sends text to Claude and gets text back.
=============================================================================
This service wraps all communication with Claude 3.5 Sonnet via Amazon Bedrock.
Every agent in the pipeline calls invoke_claude() when it needs text generation.

How it's used in the pipeline:
    - Time Parsing agent: "Convert 'yesterday' to ISO-8601 timestamps"
    - Log Analysis agent: "Summarize these CloudTrail events in 2-3 sentences"
    - Event Filter agent: "Which event categories are relevant to this question?"
    - Report Synthesis agent: "Write an audit report from these events and docs"

Why Bedrock instead of direct Anthropic API:
    Keeps the entire stack AWS-native — single credential chain (AWS IAM)
    for all services. No separate API keys for Anthropic.

Why the Converse API (not invoke_model):
    Bedrock offers two ways to call models:
    1. invoke_model() — raw JSON request/response, model-specific format
    2. converse() — standardized chat interface, same format across models

    We use converse() because it's cleaner and handles message formatting
    automatically. If we ever switch from Claude to another model on
    Bedrock, we'd only need to change the model ID — the API call stays
    the same.

Why temperature 0.0:
    Makes Claude deterministic — same input produces same output. This is
    important for time parsing (we need consistent date interpretation)
    and category selection (we need reliable comma-separated lists).

Singleton pattern:
    The boto3 client is created once and reused for all calls. Without this,
    every LLM call would create a new AWS connection (slow, wasteful).
"""

import boto3
from config import AWS_REGION, CLAUDE_MODEL_ID

# ---------------------------------------------------------------------------
# Singleton boto3 client
#
# _client starts as None. The first call to get_client() creates the actual
# AWS connection and stores it here. All subsequent calls reuse it.
# This is a module-level variable, so it persists for the lifetime of the app.
# ---------------------------------------------------------------------------
_client = None


def get_client():
    """Return the shared Bedrock Runtime client, creating it on first call.

    boto3.client("bedrock-runtime") creates a connection to the Bedrock
    Runtime service (the service that actually runs model inference).
    Note: "bedrock" (without -runtime) is for managing models, not calling them.
    """
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    return _client


def invoke_claude(system_prompt: str, user_message: str, max_tokens: int = 4096) -> str:
    """Invoke Claude 3.5 Sonnet via Bedrock Converse API. Returns the text response.

    Args:
        system_prompt: Instructions for Claude that set its behavior/role.
                       Example: "You are a time parsing assistant."
                       This is separate from the user message — Claude treats
                       system prompts as higher-priority instructions.

        user_message:  The actual input/question to process.
                       Example: "What IAM changes happened yesterday?"

        max_tokens:    Maximum number of tokens (roughly words) Claude can
                       generate in its response. Defaults to 4096.
                       - Time parsing uses 200 (small JSON response)
                       - Event summary uses 300 (2-3 sentences)
                       - Category filter uses 100 (just category names)
                       - Report generation uses 4096 (full report)

    Returns:
        The text string of Claude's response.
    """
    client = get_client()

    # Call Claude via the Converse API.
    # The Converse API uses a standardized message format:
    #   - system: list of system prompt blocks (instructions)
    #   - messages: list of user/assistant message turns
    #   - inferenceConfig: generation parameters
    response = client.converse(
        modelId=CLAUDE_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": user_message}]}],
        system=[{"text": system_prompt}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.0},
    )

    # Extract the text from the nested response structure.
    # The response looks like:
    # {
    #     "output": {
    #         "message": {
    #             "content": [{"text": "Claude's actual response here"}]
    #         }
    #     }
    # }
    return response["output"]["message"]["content"][0]["text"]
