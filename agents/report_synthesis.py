import json
import uuid
from datetime import datetime, timezone
from services.bedrock_llm import invoke_claude
from services.s3_client import store_report
from state import DocuGenState
from config import CLAUDE_MODEL_ID, CONFIDENCE_THRESHOLD

REPORT_SYSTEM_PROMPT = """\
You are an expert AWS security analyst generating an audit-ready incident report.

RULES:
- Ground every finding in the provided CloudTrail events and AWS documentation
- Reference specific event names, timestamps, and users from the log data
- Cite documentation sources by filename when making security recommendations
- If retrieval confidence is low, include a prominent disclaimer at the top
- Use clear, professional language suitable for security audits

REPORT STRUCTURE (use Markdown):
# Incident Report

## Executive Summary
(2-3 sentences overview)

## Time Range Analyzed
(Start and end timestamps)

## Timeline of Events
(Table with columns: Time, Event, User, Source IP, Category)

## Detailed Findings
(Analysis of each finding, referencing AWS documentation)

## Risk Assessment
(Low/Medium/High with justification)

## Recommended Actions
(Numbered list of concrete steps)

## Grounding & Confidence
(Retrieval confidence score, documentation sources used)
"""


def report_synthesis_node(state: DocuGenState) -> dict:
    """LangGraph node: generate the final Markdown report."""
    low_confidence = state["retrieval_confidence"] < CONFIDENCE_THRESHOLD

    # Select up to 5 events per category to ensure all categories are represented
    all_events = state["log_findings"]["events"]
    events_by_category = {}
    for e in all_events:
        cat = e.get("category", "OTHER")
        events_by_category.setdefault(cat, []).append(e)

    events_for_prompt = []
    for cat in events_by_category:
        events_for_prompt.extend(events_by_category[cat][:5])
    events_for_prompt.sort(key=lambda e: e.get("eventTime", ""))
    docs_for_prompt = [
        {
            "source": d["source"],
            "content": d["content"][:500],
            "similarity": d["similarity"],
        }
        for d in state.get("retrieved_docs", []) or []
    ]

    user_message = (
        f"Generate an audit-ready incident report based on the following data.\n\n"
        f"ORIGINAL QUESTION: {state['query']}\n\n"
        f"TIME RANGE: {json.dumps(state['time_range'])}\n\n"
        f"LOG FINDINGS ({len(state['log_findings']['events'])} total events):\n"
        f"Summary: {state['log_findings']['summary']}\n"
        f"Events (up to 5 per category, {len(events_for_prompt)} shown):\n{json.dumps(events_for_prompt, indent=2)}\n\n"
        f"RETRIEVED AWS DOCUMENTATION:\n{json.dumps(docs_for_prompt, indent=2)}\n\n"
        f"RETRIEVAL CONFIDENCE: {state['retrieval_confidence']:.2f} "
        f"(threshold: {CONFIDENCE_THRESHOLD})\n"
    )
    if low_confidence:
        user_message += (
            "WARNING: Confidence is BELOW threshold. Include a prominent disclaimer "
            "about limited documentation grounding at the top of the report.\n"
        )
    else:
        user_message += (
            "Confidence is ABOVE threshold — documentation grounding is sufficient. "
            "Do NOT include any low-confidence warnings or disclaimers.\n"
        )

    report = invoke_claude(REPORT_SYSTEM_PROMPT, user_message, max_tokens=4096)

    report_id = uuid.uuid4().hex[:8]
    sources = list(set(d["source"] for d in state.get("retrieved_docs", []) or []))

    metadata = {
        "report_id": report_id,
        "query": state["query"],
        "time_range": state["time_range"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_used": CLAUDE_MODEL_ID,
        "retrieval_confidence": state["retrieval_confidence"],
        "sources_referenced": sources,
        "event_count": len(state["log_findings"]["events"]),
    }

    return {
        "final_report": report,
        "metadata": metadata,
    }


def store_report_node(state: DocuGenState) -> dict:
    """LangGraph node: persist the report and metadata to S3."""
    store_report(
        report_id=state["metadata"]["report_id"],
        report_md=state["final_report"],
        metadata=state["metadata"],
    )
    return {}
