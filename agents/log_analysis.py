"""
Log Analysis Agent (Step 2 of the pipeline) + Event Filter (Step 3)
====================================================================
This file contains two LangGraph nodes:

1. log_analysis_node (Step 2) — Downloads CloudTrail logs from S3, extracts
   events, categorizes them, filters noise, and generates a summary.

2. event_filter_node (Step 3) — Uses Claude to determine which event
   categories are relevant to the user's question, then filters events
   to only those categories.

Why two separate nodes in one file?
    Log Analysis is about DATA COLLECTION — it gathers everything objectively.
    Event Filter is about QUESTION INTERPRETATION — it makes a subjective
    judgment about relevance. Keeping them separate means Log Analysis can
    be reused with different filtering strategies, and each step can be
    tested independently.

--- Step 2 (log_analysis_node) phases ---

Phase 2a: Build S3 paths from time range
    CloudTrail stores logs in S3 using date-based folder structure:
        AWSLogs/523761210523/CloudTrail/us-east-1/2026/02/08/
    The code converts the time range into these paths.

Phase 2b: List and filter files
    Lists all .json.gz files under each day's path. Each filename contains
    a timestamp (e.g. T1100Z = 11:00 AM UTC). Files outside the requested
    time range are skipped entirely — never downloaded.

Phase 2c: Download and decompress
    Each matching file is downloaded and decompressed (gzip). Each file
    contains a JSON Records array with a batch of events — CloudTrail
    delivers events in batches every ~5-15 minutes, not one per file.

Phase 2d: Filter by exact time range
    Even after file-level filtering, individual events may fall slightly
    outside the requested range (batch boundaries aren't clean). Each
    event's individual timestamp is checked against the exact range.

Phase 2e: Simplify and categorize each event
    Raw CloudTrail events have 50+ fields. We keep only 7:
        eventTime, eventName, userName, sourceIP, region, category, targetResource
    Category is assigned via deterministic dictionary lookup (not LLM).
    targetResource is extracted from requestParameters to distinguish
    WHO performed the action (userName) from WHAT was acted upon.

Phase 2f: Filter out noise
    AWS services constantly perform routine background operations
    (checking bucket permissions, generating encryption keys, etc.)
    that generate hundreds of events per day. These are real events but
    not security-relevant. Known noise events are separated out (not
    deleted — moved to end of list for completeness).

Phase 2g: Generate summary
    Significant events (up to 50) are sent to Claude for a 2-3 sentence
    summary. This gives the Report Synthesis agent a quick overview.

--- Step 3 (event_filter_node) ---

After Step 2, we have ALL events from the time range across all categories
(IAM, Security Groups, S3, etc.). But if the user asked "What security group
changes happened today?", sending IAM events to RAG would retrieve IAM docs
instead of security group docs, diluting the report quality.

We chose LLM-based filtering (Option B) because it gives the most precise
control. Claude reads the question, sees the available categories, and
returns only the relevant ones. Cost: ~100 tokens, ~2-3 seconds.

Input from state:
    - state["time_range"] — ISO-8601 start/end from Step 1
    - state["query"] — the user's original question

Output to state:
    - state["log_findings"] — dict with "events" list and "summary" string
    - state["relevant_categories"] — list of category strings (from Step 3)
"""

import json
from datetime import datetime, timezone
from services.bedrock_llm import invoke_claude
from services.s3_client import list_cloudtrail_files, read_cloudtrail_file
from state import DocuGenState

# ---------------------------------------------------------------------------
# Event Category Dictionary (used in Phase 2e)
#
# Maps CloudTrail event names to our internal category labels.
# This is DETERMINISTIC — just a dictionary lookup, no AI involved.
# Fast, reliable, and predictable.
#
# If an event name isn't in any of these lists, it gets categorized as "OTHER".
#
# Categories:
#   IAM_CHANGE        — User/role/policy creation, deletion, modification
#   SECURITY_GROUP    — Network firewall rule changes (VPC security groups)
#   S3_CONFIG         — Storage bucket creation, deletion, access changes
#   EC2_LIFECYCLE     — Server (instance) launch, stop, terminate, reboot
#   AUTH_EVENT        — Login attempts, session tokens, role assumptions
#   CLOUDTRAIL_CONFIG — Changes to logging/monitoring itself
# ---------------------------------------------------------------------------
EVENT_CATEGORIES = {
    "IAM_CHANGE": [
        "CreateUser", "DeleteUser", "AttachUserPolicy", "DetachUserPolicy",
        "CreateRole", "DeleteRole", "AttachRolePolicy", "DetachRolePolicy",
        "PutUserPolicy", "PutRolePolicy", "CreateAccessKey", "DeleteAccessKey",
        "UpdateAccessKey", "CreateGroup", "DeleteGroup", "AddUserToGroup",
        "RemoveUserFromGroup", "CreatePolicy", "DeletePolicy",
    ],
    "SECURITY_GROUP": [
        "AuthorizeSecurityGroupIngress", "AuthorizeSecurityGroupEgress",
        "RevokeSecurityGroupIngress", "RevokeSecurityGroupEgress",
        "CreateSecurityGroup", "DeleteSecurityGroup",
    ],
    "S3_CONFIG": [
        "CreateBucket", "DeleteBucket", "PutBucketPolicy", "DeleteBucketPolicy",
        "PutBucketAcl", "PutBucketPublicAccessBlock",
    ],
    "EC2_LIFECYCLE": [
        "RunInstances", "TerminateInstances", "StopInstances", "StartInstances",
        "RebootInstances",
    ],
    "AUTH_EVENT": [
        "ConsoleLogin", "GetSessionToken", "AssumeRole", "AssumeRoleWithSAML",
        "AssumeRoleWithWebIdentity",
    ],
    "CLOUDTRAIL_CONFIG": [
        "CreateTrail", "UpdateTrail", "DeleteTrail", "StopLogging", "StartLogging",
    ],
}


def categorize_event(event_name: str) -> str:
    """Categorize a CloudTrail event name by looking it up in EVENT_CATEGORIES.

    Loops through every category's event list. If found, returns the category
    string (e.g., "IAM_CHANGE"). If the event name isn't in any list, returns
    "OTHER" — meaning it's a valid event but not one we explicitly track.

    This is a pure dictionary lookup — no LLM call, no network request.
    """
    for category, events in EVENT_CATEGORIES.items():
        if event_name in events:
            return category
    return "OTHER"


def _parse_iso_time(time_str: str) -> datetime:
    """Parse an ISO-8601 timestamp with Z suffix into a timezone-aware datetime.

    CloudTrail uses timestamps like "2026-02-08T14:33:38Z" where Z means UTC.
    Python's fromisoformat() doesn't understand "Z" directly, so we replace
    it with "+00:00" which is the equivalent UTC offset notation.

    Returns a timezone-aware datetime object that can be compared with other
    timezone-aware datetimes (the start/end range from Step 1).
    """
    return datetime.fromisoformat(time_str.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# Noise Events (used in Phase 2f)
#
# AWS services constantly perform routine background operations that generate
# hundreds of events per day. Examples:
#   - GetBucketAcl: S3 checking its own bucket permissions
#   - GenerateDataKey: KMS generating encryption keys automatically
#   - ListBuckets: Services enumerating buckets for internal checks
#   - LookupEvents: CloudTrail checking its own logs
#
# In a typical day: ~20 significant events, ~800+ noise events.
# These are real events but NOT security-relevant for reporting.
#
# We don't delete them — they're moved to the end of the event list so
# they're still available if needed, but they don't dominate the report
# or the Claude summary.
# ---------------------------------------------------------------------------
NOISE_EVENTS = {
    "GetBucketAcl", "GetBucketVersioning", "GetBucketLocation",
    "GetBucketLogging", "GetBucketPolicy", "GetBucketTagging",
    "GetBucketEncryption", "GetBucketObjectLockConfiguration",
    "GetBucketRequestPayment", "ListBuckets", "HeadBucket",
    "GetServiceLinkedRoleDeletionStatus", "GenerateDataKey",
    "DescribeEventAggregates", "LookupEvents",
}


def _extract_target(event_name: str, params: dict) -> str:
    """Extract the target resource name from requestParameters (Phase 2e).

    This is critical for distinguishing WHO performed an action from WHAT
    was acted upon. For example:
        - "docugen-dev" (userName from userIdentity) CREATED "test-final-user"
        - Without this function, we'd only know "docugen-dev" was involved,
          and the report might say "docugen-dev was created" (wrong!)

    Different event types store the target in different requestParameters fields:
        CreateUser         -> params["userName"]     (the user being created)
        CreateRole         -> params["roleName"]     (the role being created)
        CreateGroup        -> params["groupName"]    (the group being created)
        CreateBucket       -> params["bucketName"]   (the bucket being created)
        CreateSecurityGroup-> params["groupName"]    (the security group name)
        RunInstances       -> params["instancesSet"]["items"][0]["instanceId"]
        CreateTrail        -> params["name"]         (the trail name)

    Returns empty string if the target can't be determined.
    """
    # IAM user operations (CreateUser, DeleteUser, etc.)
    if "User" in event_name:
        return params.get("userName", "")
    # IAM role operations (CreateRole, DeleteRole, etc.)
    # Exclude AssumeRole — that's an auth event, not a role modification
    if "Role" in event_name and "AssumeRole" not in event_name:
        return params.get("roleName", "")
    # IAM group operations (CreateGroup, AddUserToGroup, etc.)
    if "Group" in event_name:
        return params.get("groupName", "")
    # IAM policy operations (CreatePolicy, AttachUserPolicy, etc.)
    if "Policy" in event_name:
        return params.get("policyArn", params.get("policyName", ""))
    # Access key operations (CreateAccessKey, DeleteAccessKey)
    if "AccessKey" in event_name:
        return params.get("userName", "")
    # S3 bucket operations (CreateBucket, PutBucketPolicy, etc.)
    if "Bucket" in event_name:
        return params.get("bucketName", "")
    # Security group operations (CreateSecurityGroup, AuthorizeSecurityGroupIngress)
    if "SecurityGroup" in event_name:
        return params.get("groupName", params.get("groupId", ""))
    # EC2 instance operations (RunInstances, TerminateInstances, etc.)
    # Instance IDs are nested inside instancesSet.items array
    if "Instances" in event_name:
        instances = params.get("instancesSet", {}).get("items", [])
        if instances:
            return instances[0].get("instanceId", "")
    # CloudTrail operations (CreateTrail, UpdateTrail, etc.)
    if "Trail" in event_name:
        return params.get("name", params.get("trailName", ""))
    return ""


# ===========================================================================
#  STEP 2: LOG ANALYSIS NODE
# ===========================================================================

def log_analysis_node(state: DocuGenState) -> dict:
    """LangGraph node: read and analyze CloudTrail logs from S3.

    This is the main data collection step. It reads state["time_range"]
    (set by Step 1) and produces state["log_findings"] containing all
    categorized events and a Claude-generated summary.

    The next node (event_filter) will then filter these events based on
    the user's question.
    """
    # --- Phase 2a & 2b: Build S3 paths and list matching files ---
    # Convert the ISO-8601 strings from Step 1 into datetime objects
    # so we can compare them with event timestamps.
    start = _parse_iso_time(state["time_range"]["start"])
    end = _parse_iso_time(state["time_range"]["end"])

    # list_cloudtrail_files() (in services/s3_client.py) handles:
    #   - Building the S3 prefix paths from the date range
    #   - Listing all .json.gz files under those paths
    #   - Filtering files by timestamp embedded in filename
    # Returns a list of S3 object keys (file paths within the bucket).
    file_keys = list_cloudtrail_files(start, end)

    # --- Phase 2c: Download, decompress, and combine all events ---
    # read_cloudtrail_file() handles downloading from S3 and gzip
    # decompression. Each file contains a batch of events (not just one).
    # We combine all events from all files into a single list.
    all_events = []
    for key in file_keys:
        records = read_cloudtrail_file(key)
        all_events.extend(records)

    # --- Phase 2d & 2e: Filter by exact time and build structured events ---
    # Even though files were filtered by day/hour, individual events may
    # fall slightly outside the range (batch boundaries aren't clean).
    # We check each event's individual timestamp against the exact range.
    #
    # Simultaneously, we simplify each raw CloudTrail event (50+ fields)
    # down to our 7-field structure and assign a category.
    filtered = []
    for event in all_events:
        event_time = _parse_iso_time(event.get("eventTime", ""))
        if start <= event_time <= end:
            # Extract the actor identity (who performed the action)
            identity = event.get("userIdentity", {})
            # Extract request parameters (what was acted upon)
            # Some events have no requestParameters, so default to empty dict
            params = event.get("requestParameters") or {}
            filtered.append({
                "eventTime": event.get("eventTime", ""),
                "eventName": event.get("eventName", "Unknown"),
                # userName: who did it. Falls back to identity type (e.g., "Root")
                # if no userName field exists
                "userName": identity.get("userName") or identity.get("type", "Unknown"),
                "sourceIP": event.get("sourceIPAddress", "Unknown"),
                "region": event.get("awsRegion", "Unknown"),
                # category: deterministic lookup, not LLM-based
                "category": categorize_event(event.get("eventName", "")),
                # targetResource: what was acted upon (extracted from requestParameters)
                "targetResource": _extract_target(event.get("eventName", ""), params),
            })

    # --- Phase 2f: Separate significant events from noise ---
    # Split events into two groups:
    #   - significant: security-relevant events (not in NOISE_EVENTS set)
    #   - noise: routine AWS background operations
    # Noise events aren't deleted — they're placed at the end of the list.
    significant = [e for e in filtered if e["eventName"] not in NOISE_EVENTS]
    noise_count = len(filtered) - len(significant)

    # Use significant events for Claude's summary. If ALL events were noise
    # (unlikely but possible), fall back to using the full list.
    # Cap at 50 events to keep the prompt within reasonable token limits.
    events_for_summary = significant[:50] if significant else filtered[:50]

    # --- Phase 2g: Generate a concise summary using Claude ---
    # This summary gives the Report Synthesis agent (Step 6) a quick
    # overview of ALL events, even though it only sees a sample of them.
    # The prompt includes total counts and the user's question for context.
    summary_prompt = (
        f"Summarize these CloudTrail events in 2-3 sentences. "
        f"Focus on: what types of actions occurred, which users were active, "
        f"any notable patterns.\n"
        f"Total events: {len(filtered)} ({len(significant)} security-relevant, "
        f"{noise_count} routine AWS service calls filtered out).\n"
        f"User's original question: {state['query']}\n\n"
        f"Security-relevant events (up to 50):\n{json.dumps(events_for_summary, indent=2)}"
    )

    summary = invoke_claude(
        "You are a concise AWS security log analyst. Summarize briefly.",
        summary_prompt,
        max_tokens=300,
    )

    # Order the final event list: significant events first, then noise at end.
    # This way the most important events are at the top when the report
    # synthesis agent reads them.
    ordered_events = significant + [e for e in filtered if e["eventName"] in NOISE_EVENTS]

    # Return the findings to be merged into LangGraph shared state.
    # After this, state["log_findings"] will be available to the next node.
    return {
        "log_findings": {
            "events": ordered_events,
            "summary": summary,
        }
    }


# ===========================================================================
#  STEP 3: EVENT FILTER NODE
# ===========================================================================

def event_filter_node(state: DocuGenState) -> dict:
    """LangGraph node: use Claude to determine which event categories are relevant
    to the user's question, then filter events to only those categories.

    Why this exists (design decision):
        After Step 2, we have ALL events from the time range across all categories.
        If the user asked "What security group changes happened today?", we don't
        want IAM events going to RAG — they'd retrieve IAM documentation instead
        of security group documentation, diluting the report.

        We chose LLM-based filtering (Option B) over:
        - Option A (send everything): unfocused RAG, irrelevant docs retrieved
        - Option C (query-biased search): only biases ranking, doesn't exclude

        Cost: ~100 tokens, ~2-3 seconds. Worth it for precise filtering.

    Examples:
        "What IAM changes happened today?"
            -> Claude returns: "IAM_CHANGE"
            -> Only IAM events survive

        "Give me a full security audit for yesterday"
            -> Claude returns: "IAM_CHANGE, SECURITY_GROUP, S3_CONFIG, AUTH_EVENT, ..."
            -> All events survive
    """
    events = state["log_findings"]["events"]

    # Step 1: Find which categories actually exist in the events.
    # We only ask Claude about categories that are present — no point
    # asking about SECURITY_GROUP if there are no security group events.
    # Exclude "OTHER" since it's a catch-all, not a meaningful category.
    categories_found = list(set(e["category"] for e in events if e["category"] != "OTHER"))

    if not categories_found:
        # No categorized events found (all are OTHER), keep everything
        return {"relevant_categories": ["OTHER"]}

    # Step 2: Ask Claude which categories are relevant to the user's question.
    # The prompt includes:
    #   - The user's original question
    #   - The list of categories found in the events
    #   - Descriptions of what each category means
    #   - Instruction to return ALL categories for broad questions
    #   - Strict format: ONLY comma-separated category names, nothing else
    prompt = (
        f"The user asked: \"{state['query']}\"\n\n"
        f"We found events in these categories: {', '.join(categories_found)}\n\n"
        f"Category descriptions:\n"
        f"- IAM_CHANGE: User/role/policy creation, deletion, modification\n"
        f"- AUTH_EVENT: Login attempts, session tokens, role assumptions\n"
        f"- SECURITY_GROUP: Network firewall rule changes\n"
        f"- S3_CONFIG: Storage bucket creation, deletion, access changes\n"
        f"- EC2_LIFECYCLE: Server launch, stop, terminate\n"
        f"- CLOUDTRAIL_CONFIG: Logging/monitoring configuration changes\n\n"
        f"Which categories are relevant to the user's question? "
        f"If the question is broad (like 'what happened today' or 'security audit'), "
        f"return ALL categories.\n\n"
        f"Respond with ONLY the category names separated by commas. Nothing else."
    )

    response = invoke_claude(
        "You select relevant event categories. Respond with only category names separated by commas.",
        prompt,
        max_tokens=100,
    )

    # Step 3: Parse Claude's response into a list of categories.
    # Claude responds with something like "IAM_CHANGE, AUTH_EVENT"
    # We split by comma and strip whitespace.
    selected = [cat.strip() for cat in response.split(",")]

    # Only keep categories that actually exist in our events.
    # This guards against Claude hallucinating a category name that
    # doesn't match any real events.
    valid = [cat for cat in selected if cat in categories_found]

    # If Claude returned nothing valid (parsing issue or hallucination),
    # fall back to keeping all categories — better to show too much
    # than too little.
    if not valid:
        valid = categories_found

    # Step 4: Filter events to only the relevant categories.
    # Keep "OTHER" events too for completeness — they won't affect
    # RAG retrieval since they don't map to specific documentation.
    filtered_events = [e for e in events if e["category"] in valid or e["category"] == "OTHER"]

    # Return both the selected categories and the filtered event list.
    # - relevant_categories: used by the retrieval agent (Step 4) to build
    #   targeted RAG search queries
    # - log_findings: overwrites the previous log_findings with the filtered
    #   subset, so downstream nodes only see relevant events
    return {
        "relevant_categories": valid,
        "log_findings": {
            "events": filtered_events,
            "summary": state["log_findings"]["summary"],
        },
    }
