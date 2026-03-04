# DocuGen AI — Complete Architecture & Design Document

---

## 1. Project Overview

### What is DocuGen AI?

DocuGen AI is a multi-agent system that generates audit-ready incident reports from AWS CloudTrail logs. A user asks a natural-language question through a web interface (e.g., "What IAM changes happened yesterday?"), and the system orchestrates multiple specialized agents through a pipeline to analyze cloud activity logs, retrieve relevant AWS documentation, and produce a grounded, traceable security report.

### What Problem Does It Solve?

In real AWS environments, security teams need to investigate incidents by manually digging through CloudTrail logs, cross-referencing AWS documentation, and writing reports. This is slow, error-prone, and requires deep AWS expertise.

DocuGen AI automates this entire workflow. The key innovation is that reports are **documentation-grounded** — every finding, risk assessment, and recommendation is backed by actual AWS documentation retrieved through RAG (Retrieval-Augmented Generation), not just the LLM's training data. This makes the reports auditable and verifiable.

### What This Project Demonstrates

| Capability | How It's Demonstrated |
|---|---|
| **Multi-agent orchestration** | 5 specialized agents coordinated through LangGraph with conditional branching |
| **RAG (Retrieval-Augmented Generation)** | Vector search over AWS documentation using Pinecone, with confidence gating |
| **Hallucination control** | Confidence threshold prevents report generation without sufficient documentation grounding |
| **Cloud-native architecture** | Real AWS services (CloudTrail, S3, Bedrock) — not simulations |
| **Query-aware filtering** | LLM-based event filtering ensures only relevant data reaches the report |
| **Grounding & traceability** | Every recommendation cites a specific documentation source |

---

## 2. Tech Stack

### Models (via Amazon Bedrock)

Amazon Bedrock is an AWS service that hosts AI models from multiple providers (Anthropic, Meta, Amazon, etc.). We access two models through it:

| Model | ID | Purpose |
|---|---|---|
| **Claude 3.5 Sonnet** (by Anthropic) | `us.anthropic.claude-3-5-sonnet-20241022-v2:0` | Text generation — time parsing, event summarization, category filtering, report writing |
| **Titan Embeddings V2** (by Amazon) | `amazon.titan-embed-text-v2:0` | Converts text into numerical vectors (1024 dimensions) for semantic search |

**Why Bedrock instead of direct API calls:**
- Keeps the entire stack AWS-native — single credential chain (AWS IAM) for all services
- No separate API keys for Anthropic or other providers
- Demonstrates cloud-native architecture

**Why Claude 3.5 Sonnet:**
- Strong reasoning for report synthesis
- Good instruction-following for structured extraction (time parsing, category selection)
- Available natively through Bedrock

**Why Titan Embeddings V2:**
- Native to Bedrock — same credential chain as Claude
- 1024 dimensions provides good semantic resolution for document search
- No external embedding provider needed

### Vector Database: Pinecone

| Setting | Value |
|---|---|
| Index name | `docugen-aws-docs` |
| Dimensions | 1024 (matches Titan Embeddings V2) |
| Similarity metric | Cosine |
| Plan | Starter (free tier) |

**Why Pinecone (not FAISS or ChromaDB):**
- Managed cloud service — no local infrastructure to maintain
- Demonstrates real vector database usage (more realistic than local FAISS)
- Free tier is sufficient (~100 document chunks)
- Production-grade querying with metadata filtering

**Why cosine similarity:**
Cosine similarity measures the angle between two vectors, ignoring their length. This means a short text chunk and a long text chunk about the same topic will score similarly — it captures semantic meaning regardless of document length.

### Orchestration: LangGraph

LangGraph is a framework for building multi-agent workflows as directed graphs. Each agent is a "node" in the graph, and "edges" define the flow between them.

**Why LangGraph:**
- Built for multi-agent workflows with conditional routing
- Supports loops (needed for the retrieval retry mechanism)
- Shared state object makes inter-agent communication simple
- Industry-standard for agentic AI systems

### UI: Streamlit

**Why Streamlit:**
- Fastest way to build a Python-native web UI for AI applications
- Built-in Markdown rendering (perfect for displaying reports)
- Built-in download button for report export
- No frontend framework (React, etc.) needed

### AWS Services

| Service | Purpose | Cost |
|---|---|---|
| **CloudTrail** | Records all AWS API activity as event logs | Free (1 management event trail) |
| **S3** (logs bucket) | Stores CloudTrail log files as compressed `.json.gz` | Negligible |
| **S3** (reports bucket) | Stores generated reports and metadata | Negligible |
| **Bedrock** | Hosts Claude 3.5 Sonnet and Titan Embeddings V2 | Pay-per-token |

### Dependencies

| Package | Version | Purpose |
|---|---|---|
| `langgraph` | 0.2.60 | Multi-agent orchestration framework |
| `langchain-text-splitters` | 0.3.4 | Document chunking for RAG indexing |
| `boto3` | 1.35.86 | AWS SDK for Python (S3, Bedrock) |
| `pinecone-client` | 5.0.1 | Pinecone vector database client |
| `streamlit` | 1.41.1 | Web UI framework |
| `python-dotenv` | 1.0.1 | Environment variable loading |
| `pytest` | 8.3.4 | Testing framework |

---

## 3. System Architecture

### Pipeline Flow

```
User types: "What IAM changes happened yesterday?"
        |
        v
+--------------------+
|  1. Time Parsing   |  Claude extracts time range from natural language
+--------+-----------+
         |
         v
+--------------------+
|  2. Log Analysis   |  Downloads CloudTrail logs from S3, categorizes events
+--------+-----------+
         |
         v
+--------------------+
|  3. Event Filter   |  Claude selects categories relevant to the question
+--------+-----------+
         |
         v
+--------------------+
|  4. Retrieval      |  Searches Pinecone for relevant AWS documentation
+--------+-----------+
         |
         v
+--------------------+
|  5. Confidence     |  Is confidence >= 0.50?
|     Check          |  Yes -> proceed | No -> retry (max 2 times)
+--------+-----------+
         |
         v
+--------------------+
|  6. Report         |  Claude combines events + docs + question into report
|     Synthesis      |
+--------+-----------+
         |
         v
+--------------------+
|  7. Store Report   |  Saves report + metadata to S3
+--------------------+
         |
         v
    Report displayed in Streamlit
```

### LangGraph Wiring

```
START -> time_parsing -> log_analysis -> event_filter -> retrieval
                                                            |
                                                     confidence_check
                                                       |          |
                                                    "retry"   "sufficient"
                                                       |          |
                                                 increment_retry  |
                                                       |          |
                                                    retrieval     |
                                                            report_synthesis -> store_report -> END
```

### Bedrock API Calls Per Pipeline Run

| Step | Model | Purpose | Max Tokens |
|---|---|---|---|
| 1. Time Parsing | Claude 3.5 Sonnet | Extract time range | 200 |
| 2. Log Analysis | Claude 3.5 Sonnet | Summarize events | 300 |
| 3. Event Filter | Claude 3.5 Sonnet | Select relevant categories | 100 |
| 4. Retrieval | Titan Embeddings V2 | Convert query to vector | N/A |
| 6. Report Synthesis | Claude 3.5 Sonnet | Write the full report | 4096 |

Total: **4 Claude calls + 1 Titan Embeddings call** per pipeline run (assuming no retries).

---

## 4. Detailed Step-by-Step Walkthrough

### Step 1: Time Parsing

**File:** `agents/time_parsing.py`

**What it does:** Takes the user's natural-language question and extracts a precise ISO-8601 time range using Claude.

**How it works:**
1. Gets the current date/time and includes it in the prompt so Claude knows what "today" or "yesterday" means
2. Sends the user's question to Claude with rules for interpreting time expressions
3. Claude returns a JSON object with `start` and `end` timestamps
4. The code strips any markdown formatting and parses the JSON

**Example:**
```
Input:  "What IAM changes happened yesterday?"
Output: {"start": "2026-02-08T00:00:00Z", "end": "2026-02-08T23:59:59Z"}
```

**Time expressions handled:**
- "today", "yesterday", "last Tuesday", "3 days ago"
- "morning" (00:00-12:00), "afternoon" (12:00-18:00), "evening" (18:00-23:59)
- "between 2pm and 5pm yesterday"
- If no time specified, defaults to the full day (00:00 to 23:59)

**Design choice — why use an LLM for this:**
Time parsing could be done with regex or a library like `dateparser`. However, using Claude handles edge cases naturally ("last Tuesday morning", "the past 48 hours") without writing complex parsing rules. The cost is minimal (~200 tokens per call).

---

### Step 2: Log Analysis

**File:** `agents/log_analysis.py`

**What it does:** Downloads CloudTrail log files from S3 for the given time range, extracts all events, categorizes them, and filters out noise.

**How it works, phase by phase:**

#### Phase 2a: Build S3 paths from the time range

CloudTrail stores log files in S3 using a structured naming convention that includes the date:
```
AWSLogs/523761210523/CloudTrail/us-east-1/2026/02/08/
```

The code converts the time range into these paths. For multi-day ranges, it creates one path per day.

#### Phase 2b: List and filter files

The code asks S3 for all `.json.gz` files under each day's path. Each filename contains a timestamp (e.g., `T1100Z` = 11:00 AM UTC). The code extracts this timestamp and checks if it falls within the requested range. Files outside the range are skipped entirely — they're never downloaded.

#### Phase 2c: Download and decompress

Each matching file is downloaded from S3 and decompressed (CloudTrail uses gzip compression). Each decompressed file contains a JSON `Records` array with a batch of events — CloudTrail delivers events in batches every ~5-15 minutes, not one file per event.

All events from all files are combined into a single list.

#### Phase 2d: Filter by exact time range

Even though files were filtered by day, individual events inside a file might fall slightly outside the requested range (batch boundaries aren't perfectly clean). The code checks each event's individual timestamp against the exact range. For a query like "between 2pm and 3pm", this removes events from outside that window.

#### Phase 2e: Simplify and categorize each event

Each raw CloudTrail event has 50+ fields. The code keeps only 7 fields:

| Field | Source | Example |
|---|---|---|
| `eventTime` | Directly from CloudTrail | `2026-02-08T14:33:38Z` |
| `eventName` | Directly from CloudTrail | `CreateRole` |
| `userName` | From `userIdentity` — who performed the action | `docugen-dev` |
| `sourceIP` | Directly from CloudTrail | `45.240.199.159` |
| `region` | Directly from CloudTrail | `us-east-1` |
| `category` | Assigned by our code via dictionary lookup | `IAM_CHANGE` |
| `targetResource` | Extracted from `requestParameters` — what was acted upon | `test-final-user` |

**Categorization** uses a predefined dictionary mapping event names to categories:
```
CreateUser, DeleteUser, AttachUserPolicy, ...        -> IAM_CHANGE
ConsoleLogin, AssumeRole, ...                        -> AUTH_EVENT
CreateSecurityGroup, AuthorizeSecurityGroupIngress   -> SECURITY_GROUP
CreateBucket, PutBucketPolicy, ...                   -> S3_CONFIG
RunInstances, TerminateInstances, ...                -> EC2_LIFECYCLE
CreateTrail, StopLogging, ...                        -> CLOUDTRAIL_CONFIG
Anything not in the above lists                      -> OTHER
```

This is deterministic (no AI involved) — just a dictionary lookup. Fast and reliable.

**Target resource extraction** (`_extract_target` function) reads `requestParameters` to identify what was acted upon. Different event types store this in different fields:
- CreateUser → `requestParameters.userName` (the user being created)
- CreateBucket → `requestParameters.bucketName` (the bucket being created)
- CreateSecurityGroup → `requestParameters.groupName` (the security group being created)

This is important because `userName` (from `userIdentity`) tells us **who** performed the action, while `targetResource` (from `requestParameters`) tells us **what** was acted upon. Without this distinction, the report might confuse the actor with the target.

#### Phase 2f: Filter out noise

AWS services constantly perform routine background operations (checking bucket permissions, generating encryption keys, etc.) that generate hundreds of events per day. These are real events but not security-relevant. The code has a predefined set of known noise events:

```
GetBucketAcl, GetBucketVersioning, ListBuckets,
GenerateDataKey, DescribeEventAggregates, ...
```

Events matching these names are separated from significant events. In a typical day: ~20 significant events, ~800+ noise events. Noise events are not deleted — they're moved to the end of the list for completeness.

#### Phase 2g: Generate summary

The significant events (up to 50) are sent to Claude for a 2-3 sentence summary. This summary gives the Report Synthesis agent a quick overview of all events, even though it only sees a sample in Step 6. The prompt includes the total event count and noise count for context.

**What this step does NOT do:** It does not filter events based on the user's question. It collects everything from the time range. The question-based filtering happens in the next step.

---

### Step 3: Event Filter

**File:** `agents/log_analysis.py` (`event_filter_node` function)

**What it does:** Uses Claude to determine which event categories are relevant to the user's question, then filters events to only those categories.

**Why this step exists (design decision):**

After Step 2, we have all events from the time range across all categories (IAM, Security Groups, S3, etc.). But if the user asked "What security group changes happened today?", sending IAM events to RAG would retrieve IAM documentation instead of security group documentation, diluting the report quality.

We considered three approaches:

| Option | Approach | Tradeoff |
|---|---|---|
| A. Send everything | Don't filter, let Claude sort it out in the report | Unfocused RAG, irrelevant docs retrieved |
| B. LLM-based filtering | Ask Claude which categories match the question | Extra LLM call, but precise filtering |
| C. Query-biased search | Add the question to the RAG search query to bias results | No extra cost, but only biases ranking — doesn't exclude |

**We chose Option B** because it gives the most precise control. When the user asks about a specific topic, RAG retrieves only documentation for that topic. The extra LLM call costs ~100 tokens (minimal) and adds ~2-3 seconds.

**How it works:**
1. Collects all unique categories found in the events
2. Sends them to Claude along with the user's question and category descriptions
3. Claude responds with just the relevant category names (e.g., "SECURITY_GROUP")
4. Events are filtered to only keep events from the selected categories
5. For broad questions like "full security audit", Claude returns all categories

**Examples:**
```
Question: "What IAM changes happened today?"
Claude returns: "IAM_CHANGE"
Result: Only IAM events survive, RAG searches for IAM docs

Question: "Give me a full security audit for yesterday"
Claude returns: "IAM_CHANGE, SECURITY_GROUP, S3_CONFIG, AUTH_EVENT, EC2_LIFECYCLE, CLOUDTRAIL_CONFIG"
Result: All events survive, RAG searches for all doc types

Question: "Were any S3 buckets modified yesterday?"
Claude returns: "S3_CONFIG"
Result: Only S3 events survive, RAG searches for S3 docs
```

---

### Step 4: Retrieval (RAG)

**File:** `agents/retrieval.py`

**What it does:** Searches the Pinecone vector database for AWS documentation chunks relevant to the filtered event categories.

#### How RAG works in this project

**Setup phase (one-time, on first run):**
1. 12 curated AWS documentation files (Markdown) are read from `docs/aws/`
2. Each file is split into smaller chunks (~1000 characters each, with 200-character overlap)
3. Each chunk is converted into a 1024-dimensional numerical vector by Titan Embeddings V2
4. All vectors are stored in the Pinecone index `docugen-aws-docs`
5. On subsequent runs, this step is skipped (the index already has data)

**Query phase (every pipeline run):**
1. The code looks at the `relevant_categories` from Step 3
2. Builds a natural-language search query based on those categories:
   ```
   IAM_CHANGE     -> "IAM users roles policies best practices least privilege credentials"
   SECURITY_GROUP -> "EC2 security groups inbound outbound rules network access"
   S3_CONFIG      -> "S3 bucket policies access control public access encryption"
   ```
3. This query text is converted into a 1024-dimensional vector by Titan Embeddings V2
4. Pinecone compares this vector against all stored document chunk vectors using cosine similarity
5. The top 5 most similar chunks are returned, each with a similarity score (0 to 1)

**Why we don't search with the user's question directly:**

The user asks about their **logs** (e.g., "What IAM changes happened?"), but Pinecone contains **AWS documentation** (best practices, security guides). Searching with the user's question would produce poor results because the docs don't discuss what happened in the user's account.

Instead, we search using the **event categories** as natural-language queries. This way, if IAM events were detected, we retrieve IAM best practices documentation — which is exactly what the report needs to cite.

**Retry logic with query broadening:**
```
Attempt 1: Category-specific query
  "IAM users roles policies best practices least privilege credentials"

Attempt 2: Broader security context
  "AWS security best practices shared responsibility model monitoring access control"

Attempt 3: Broadest possible
  "AWS cloud security IAM identity access management incident response compliance"
```

Each retry broadens the search to increase the chance of finding relevant documentation.

---

### Step 5: Confidence Check

**File:** `agents/retrieval.py` (`confidence_check` function)

**What it does:** Decides whether the retrieved documentation is good enough to proceed with report generation.

**How confidence is calculated:**
```
confidence = average cosine similarity of the top 5 retrieved chunks
```

For example, if the 5 chunks have similarities [0.72, 0.65, 0.61, 0.58, 0.51]:
```
confidence = (0.72 + 0.65 + 0.61 + 0.58 + 0.51) / 5 = 0.61
```

**Decision logic:**
```
IF confidence >= 0.50:
    -> "sufficient" — proceed to report synthesis

IF confidence < 0.50 AND retry_count < 2:
    -> "retry" — increment retry counter, broaden query, search again

IF confidence < 0.50 AND retry_count >= 2:
    -> "sufficient" — proceed anyway, but with a low-confidence warning in the report
```

**Why 0.50 (not higher)?**

The threshold was initially set at 0.75 but was lowered to 0.50 after testing. Amazon Titan Embeddings V2 produces lower cosine similarity scores compared to other embedding models — typical scores range from 0.45 to 0.70 for relevant matches. A threshold of 0.75 would reject almost all retrievals, including clearly relevant ones.

The 0.50 threshold was calibrated through real testing: scores above 0.50 consistently returned relevant documentation, while scores below 0.50 returned genuinely poor matches.

**Why this prevents hallucination:**

Without this confidence gate, the LLM might fabricate AWS service behaviors, cite incorrect policy syntax, or invent security implications. By requiring documentation grounding first, every claim in the report can be traced back to a real documentation chunk. If grounding is insufficient, the report includes a visible disclaimer.

---

### Step 6: Report Synthesis

**File:** `agents/report_synthesis.py`

**What it does:** Combines everything — events, documentation, and the user's question — into a single prompt and asks Claude to write an audit-ready Markdown report.

**What Claude receives in the prompt:**
1. **The user's original question** — tells Claude what to focus on
2. **Filtered events** (up to 5 per category, sorted chronologically) — the factual data
3. **AWS documentation chunks** (5 chunks from Pinecone) — the grounding context
4. **Event summary** from Step 2 — the big picture overview
5. **Confidence score and threshold** — so Claude knows whether to add disclaimers

**Report structure (enforced via system prompt):**
```
# Incident Report
## Executive Summary        (2-3 sentences overview)
## Time Range Analyzed      (start and end timestamps)
## Timeline of Events       (table: time, event, user, source IP, category)
## Detailed Findings        (analysis citing AWS documentation)
## Risk Assessment          (Low/Medium/High with justification)
## Recommended Actions      (numbered list citing documentation sources)
## Grounding & Confidence   (confidence score, documentation sources used)
```

**How the three data sources work together:**
- **Events** tell Claude **what happened** — "CreateUser was performed by docugen-dev targeting test-final-user"
- **Documentation** tells Claude **why it matters** — "According to iam-best-practices.md, root account should not be used for daily tasks"
- **The question** tells Claude **what to focus on** — if you asked about IAM, the report focuses on IAM findings

**Low confidence handling:**
- If confidence is above the threshold, the prompt explicitly tells Claude: "Do NOT include any low-confidence warnings"
- If confidence is below the threshold, the prompt says: "Include a prominent disclaimer about limited documentation grounding"

---

### Step 7: Store Report

**File:** `agents/report_synthesis.py` (`store_report_node` function) and `services/s3_client.py`

**What it does:** Saves the generated report and its metadata to the S3 reports bucket.

**Two files are created:**
```
s3://docugen-reports-523761210523/
  reports/
    2026-02-09/
      f3def3b3-report.md          <- The Markdown report
      f3def3b3-metadata.json      <- Metadata for audit traceability
```

**Metadata includes:**
```json
{
  "report_id": "f3def3b3",
  "query": "What IAM changes happened today?",
  "time_range": {"start": "...", "end": "..."},
  "generated_at": "2026-02-09T20:23:45Z",
  "model_used": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
  "retrieval_confidence": 0.63,
  "sources_referenced": ["iam-best-practices.md", "iam-users-guide.md"],
  "event_count": 899
}
```

**Why store in S3:**
- Reports persist beyond the application session
- Metadata provides full traceability of how each report was generated
- Mirrors real-world practice — production security tools store artifacts in S3

---

## 5. RAG Architecture in Detail

### What is RAG?

RAG (Retrieval-Augmented Generation) is a technique that gives an LLM access to specific knowledge by retrieving relevant documents before generating a response. Instead of relying on the LLM's training data (which may be outdated or wrong), RAG provides actual documents for the LLM to reference.

### Why RAG is Necessary for This Project

Without RAG, the report would be:
- **Events** (factual, from CloudTrail): "CreateUser was performed by Root at 11:18"
- **Analysis** (from Claude's training data): "This might be a security risk" — unverifiable, possibly hallucinated

With RAG, the report becomes:
- **Events** (factual): "CreateUser was performed by Root at 11:18"
- **Analysis** (grounded): "According to **iam-best-practices.md**, 'AWS strongly recommends that you do not use the root user for everyday tasks.' This is a HIGH risk finding."

The difference: every recommendation now has a **citable source**. An auditor can verify the recommendation by reading the referenced document.

### Document Pipeline

```
12 AWS Markdown files (docs/aws/)
        |
        v
Split into chunks (RecursiveCharacterTextSplitter)
  - Chunk size: 1000 characters
  - Overlap: 200 characters
  - Result: ~94 chunks total
        |
        v
Each chunk -> Titan Embeddings V2 -> 1024-dimensional vector
        |
        v
All vectors stored in Pinecone index "docugen-aws-docs"
  - Each vector has metadata: {content, source filename, chunk index}
```

### Documentation Sources

| File | Topic | Used When |
|---|---|---|
| `iam-users-guide.md` | IAM user creation, management, permissions | IAM_CHANGE events |
| `iam-policies-guide.md` | IAM policy types, structure, evaluation | IAM_CHANGE events |
| `iam-best-practices.md` | Root account security, MFA, least privilege | IAM_CHANGE events |
| `iam-roles-guide.md` | IAM roles, delegation, trust policies | IAM_CHANGE events |
| `ec2-instances-guide.md` | EC2 instance lifecycle, security | EC2_LIFECYCLE events |
| `ec2-security-groups.md` | Security group rules, best practices | SECURITY_GROUP events |
| `s3-buckets-guide.md` | S3 bucket creation, configuration | S3_CONFIG events |
| `s3-access-control.md` | S3 access policies, public access blocking | S3_CONFIG events |
| `cloudtrail-overview.md` | CloudTrail concepts, trail configuration | CLOUDTRAIL_CONFIG events |
| `cloudtrail-log-format.md` | CloudTrail event structure, fields | General reference |
| `lambda-overview.md` | Lambda functions, permissions | General reference |
| `aws-security-fundamentals.md` | Shared responsibility model, security basics | Broad queries |

### Chunking Strategy

| Parameter | Value | Reasoning |
|---|---|---|
| Chunk size | 1000 characters | Large enough to capture a complete concept (a paragraph or section), small enough for precise retrieval |
| Overlap | 200 characters | Prevents losing context at chunk boundaries — a sentence split across chunks remains findable in both |
| Splitter | RecursiveCharacterTextSplitter | Tries to split on paragraphs first, then sentences, then words — preserves natural text structure |

### Why Search by Event Categories (Not by User Question)

The user asks about their **logs**: "What IAM changes happened today?"
The documents in Pinecone are about **AWS best practices**: "Enable MFA for all users..."

Searching Pinecone with the user's question would produce poor results because the docs don't discuss what happened in the user's account today. Instead, the system:

1. Detects which event categories were found (IAM_CHANGE, SECURITY_GROUP, etc.)
2. Builds natural-language queries from those categories
3. Searches Pinecone with these category-based queries

This ensures the retrieved docs match the **type of activity detected**, which is exactly what the report needs to cite.

---

## 6. Shared State Object

All agents communicate through a single shared state dictionary managed by LangGraph. Each agent reads what it needs and writes its output back.

```python
{
    "query": str,                    # Original user question
    "time_range": {                  # From Step 1: Time Parsing
        "start": str,                #   ISO-8601 timestamp
        "end": str                   #   ISO-8601 timestamp
    },
    "log_findings": {                # From Step 2: Log Analysis
        "events": list,              #   Categorized CloudTrail events
        "summary": str               #   2-3 sentence overview
    },
    "relevant_categories": list,     # From Step 3: Event Filter
    "retrieved_docs": list,          # From Step 4: Retrieval
    "retrieval_confidence": float,   # From Step 4: 0.0 to 1.0
    "retry_count": int,              # Retrieval retry counter
    "final_report": str,             # From Step 6: Markdown report
    "metadata": dict                 # Report metadata for audit trail
}
```

**Why a single flat state:**
- **Transparent:** Every agent can see the full pipeline state
- **Debuggable:** You can inspect the state at any point in the graph
- **Simple:** No complex message passing between agents
- **LangGraph-native:** This is exactly how LangGraph state management works

---

## 7. Event Structure

Each event in `log_findings.events` has this structure:

```json
{
    "eventTime": "2026-02-08T14:33:38Z",
    "eventName": "CreateUser",
    "userName": "docugen-dev",
    "sourceIP": "45.240.199.159",
    "region": "us-east-1",
    "category": "IAM_CHANGE",
    "targetResource": "test-final-user"
}
```

| Field | Source | Description |
|---|---|---|
| `eventTime` | CloudTrail | When the action occurred |
| `eventName` | CloudTrail | The AWS API action (e.g., CreateUser) |
| `userName` | CloudTrail `userIdentity` | **Who** performed the action |
| `sourceIP` | CloudTrail | IP address of the actor |
| `region` | CloudTrail | AWS region where it happened |
| `category` | Our code (dictionary lookup) | Event classification |
| `targetResource` | CloudTrail `requestParameters` | **What** was acted upon |

The distinction between `userName` and `targetResource` is critical. For `CreateUser`:
- `userName` = "docugen-dev" (the person who ran the command)
- `targetResource` = "test-final-user" (the user that was created)

Without `targetResource`, the report might confuse the actor with the target.

### Event Categories

| Category | Events | Description |
|---|---|---|
| `IAM_CHANGE` | CreateUser, DeleteUser, AttachUserPolicy, CreateRole, CreateAccessKey, ... | Identity and access management changes |
| `AUTH_EVENT` | ConsoleLogin, AssumeRole, GetSessionToken, ... | Authentication and session events |
| `SECURITY_GROUP` | CreateSecurityGroup, AuthorizeSecurityGroupIngress, ... | Network firewall rule changes |
| `S3_CONFIG` | CreateBucket, DeleteBucket, PutBucketPolicy, PutBucketPublicAccessBlock, ... | Storage configuration changes |
| `EC2_LIFECYCLE` | RunInstances, TerminateInstances, StopInstances, ... | Server lifecycle events |
| `CLOUDTRAIL_CONFIG` | CreateTrail, DeleteTrail, StopLogging, ... | Logging configuration changes |
| `OTHER` | Everything not in the above lists | Uncategorized events |

### Noise Events

AWS services generate hundreds of routine background events daily. These are filtered out to prevent drowning the significant events:

```
GetBucketAcl, GetBucketVersioning, GetBucketLocation,
GetBucketLogging, GetBucketPolicy, GetBucketTagging,
GetBucketEncryption, ListBuckets, HeadBucket,
GenerateDataKey, DescribeEventAggregates, LookupEvents, ...
```

Noise events are not deleted — they're moved to the end of the events list. The total count (including noise) is preserved in the report metadata.

---

## 8. CloudTrail & S3 Architecture

### What is CloudTrail?

CloudTrail is AWS's audit logging service. Every API call made in your AWS account — whether from the console, CLI, or SDK — is recorded as an event and delivered to S3 as a compressed JSON file.

### How Logs Are Organized in S3

```
s3://docugen-cloudtrail-logs-523761210523/
  AWSLogs/523761210523/CloudTrail/us-east-1/
    2026/
      02/
        08/
          523761210523_CloudTrail_us-east-1_20260208T1100Z_abc123.json.gz
          523761210523_CloudTrail_us-east-1_20260208T1130Z_def456.json.gz
          ...
```

**Important:** S3 doesn't have real folders. The slashes in the file name (called the "key") simulate a folder structure. S3 lets you search by prefix, which makes it behave like folders.

### How CloudTrail Delivers Events

CloudTrail doesn't write one file per event. Instead, it **batches** events collected over a ~5-15 minute window into a single compressed `.json.gz` file. So one file might contain 10-100+ events.

A decompressed file looks like:
```json
{
    "Records": [
        {"eventTime": "...", "eventName": "CreateUser", ...},
        {"eventTime": "...", "eventName": "GetBucketAcl", ...},
        {"eventTime": "...", "eventName": "AttachUserPolicy", ...}
    ]
}
```

This means there's a **~15-minute delay** before new events become available — CloudTrail is still collecting events into the next batch.

### Three Layers of Filtering

| Layer | Where | What It Does | Precision |
|---|---|---|---|
| Folder prefix | `s3_client.py` | Only looks at the right day's files | Day-level |
| File timestamp | `s3_client.py` | Only downloads files within the time range | ~15-minute level |
| Event timestamp | `log_analysis.py` | Only keeps events within the exact range | Second-level |

Each layer narrows the data further. For "what happened today", all three layers keep everything. For "what happened between 2pm and 3pm", the event-level filter removes events outside that window.

### Trail Configuration

| Setting | Value | Reasoning |
|---|---|---|
| Event types | Management events only | Free for 1 trail, most security-relevant, avoids massive data volume |
| Read + Write | Both | Full picture for incident analysis |
| Encryption | SSE-S3 default | KMS adds cost and complexity, not needed for a dev project |
| CloudWatch Logs | Disabled | We only need logs in S3 |
| Multi-region | No | Single region keeps things simple |

---

## 9. Report Storage & Audit Trail

### S3 Bucket Layout

```
s3://docugen-reports-523761210523/
  reports/
    2026-02-08/
      f3def3b3-report.md
      f3def3b3-metadata.json
    2026-02-09/
      12f3a66b-report.md
      12f3a66b-metadata.json
```

### Report Format

Reports are Markdown files containing:
- Executive summary
- Time range analyzed
- Timeline of events (table format)
- Detailed findings with documentation citations
- Risk assessment (Low/Medium/High)
- Recommended actions with source references
- Grounding & confidence metadata

### Report Metadata

```json
{
    "report_id": "f3def3b3",
    "query": "What IAM changes happened today?",
    "time_range": {"start": "...", "end": "..."},
    "generated_at": "2026-02-08T13:41:52Z",
    "model_used": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "retrieval_confidence": 0.63,
    "sources_referenced": ["iam-best-practices.md", "iam-users-guide.md"],
    "event_count": 899
}
```

Every report has full traceability: what was asked, when it was generated, which model was used, what documentation was referenced, and how confident the system was.

---

## 10. Infrastructure Setup

### AWS Account

| Resource | Value |
|---|---|
| Account ID | 523761210523 |
| Region | us-east-1 |
| IAM User | `docugen-dev` |
| Policies | AmazonS3FullAccess, AmazonBedrockFullAccess, CloudWatchLogsReadOnlyAccess, IAMFullAccess, AmazonEC2FullAccess, AWSCloudTrail_FullAccess |

### S3 Buckets

| Bucket | Purpose |
|---|---|
| `docugen-cloudtrail-logs-523761210523` | CloudTrail log delivery |
| `docugen-reports-523761210523` | Generated reports + metadata |

### Pinecone

| Setting | Value |
|---|---|
| Index name | `docugen-aws-docs` |
| Dimensions | 1024 |
| Metric | Cosine |
| Plan | Starter (free) |

### Credentials

All credentials are loaded via environment variables (`.env` file) or `~/.aws/credentials`. Nothing is hardcoded in the source code.

| Variable | Source |
|---|---|
| `AWS_ACCESS_KEY_ID` | AWS IAM console |
| `AWS_SECRET_ACCESS_KEY` | AWS IAM console |
| `AWS_DEFAULT_REGION` | `us-east-1` |
| `PINECONE_API_KEY` | Pinecone dashboard |

---

## 11. Testing Strategy

### Test Suite: 18 tests across 5 files

| File | Tests | What It Covers |
|---|---|---|
| `test_time_parsing.py` | 3 | Time range extraction, markdown fence stripping, Claude prompt validation |
| `test_log_analysis.py` | 7 | Event categorization for all 6 categories + unknown events |
| `test_retrieval.py` | 5 | Confidence check logic, threshold boundary, query broadening on retry |
| `test_report_synthesis.py` | 2 | Report generation with metadata, low-confidence warning inclusion |
| `test_graph.py` | 1 | Full pipeline integration test with all services mocked |

### Mocking Strategy

All external services (Bedrock, S3, Pinecone) are mocked in tests to:
- Avoid costs (no real Bedrock calls)
- Ensure reproducibility (deterministic responses)
- Enable offline testing

The `conftest.py` uses a `MultiMock` class that patches `invoke_claude` at the agent import level (not the service level), ensuring mocks work correctly with Python's import system.

### Running Tests

```
python -m pytest tests/ -v
```

---

## 12. File Structure

```
DocuGen-AI/
  config.py                     # Centralized constants (model IDs, thresholds, bucket names)
  state.py                      # LangGraph TypedDict shared state definition
  graph.py                      # LangGraph pipeline wiring (nodes + edges)
  app.py                        # Streamlit web UI
  requirements.txt              # Python dependencies
  .env                          # Environment variables (credentials — not committed)
  .env.example                  # Template for required env vars
  .gitignore                    # Prevents credentials/venv from being committed

  agents/
    time_parsing.py             # Step 1: Natural language -> ISO-8601 time range
    log_analysis.py             # Step 2: S3 log reading + categorization + noise filtering
                                # Step 3: Event filter (LLM-based category selection)
    retrieval.py                # Step 4: Pinecone RAG search + confidence check
    report_synthesis.py         # Step 6: Report generation + S3 storage

  services/
    bedrock_llm.py              # Claude 3.5 Sonnet wrapper (Bedrock Converse API)
    bedrock_embeddings.py       # Titan Embeddings V2 wrapper (Bedrock invoke_model API)
    s3_client.py                # S3 operations (read logs, store reports)
    pinecone_client.py          # Pinecone operations (upsert, query, index_has_data)
    indexer.py                  # First-run document indexing pipeline

  docs/aws/
    iam-users-guide.md          # 12 curated AWS documentation files
    iam-policies-guide.md       # Used as the knowledge base for RAG
    iam-best-practices.md
    iam-roles-guide.md
    ec2-instances-guide.md
    ec2-security-groups.md
    s3-buckets-guide.md
    s3-access-control.md
    cloudtrail-overview.md
    cloudtrail-log-format.md
    lambda-overview.md
    aws-security-fundamentals.md

  tests/
    conftest.py                 # Shared fixtures + mock setup
    test_time_parsing.py
    test_log_analysis.py
    test_retrieval.py
    test_report_synthesis.py
    test_graph.py               # Full pipeline integration test
```

---

## 13. Design Decisions Summary

| Decision | Choice | Why |
|---|---|---|
| LLM provider | Amazon Bedrock | AWS-native, single credential chain, no external API keys |
| LLM model | Claude 3.5 Sonnet | Strong reasoning, good instruction-following, available on Bedrock |
| Embedding model | Titan Embeddings V2 | Native to Bedrock, 1024 dimensions, same credential chain |
| Vector database | Pinecone (free tier) | Managed service, production-grade, demonstrates real vector DB usage |
| Orchestration | LangGraph | Built for multi-agent workflows, supports conditional edges and loops |
| UI | Streamlit | Fast to build, Python-native, built-in Markdown rendering |
| Log source | S3 (not CloudTrail API) | Full history access, no rate limits, realistic production pattern |
| Event categorization | Dictionary lookup (not LLM) | Deterministic, fast, reliable — no need for AI on a simple classification |
| Event filtering | LLM-based (Option B) | Precise question-to-category mapping, handles both specific and broad queries |
| Confidence threshold | 0.50 | Calibrated for Titan Embeddings V2 score distribution (0.45-0.70 range) |
| Max retries | 2 (3 total attempts) | Balances thoroughness with latency |
| Chunk size | 1000 chars, 200 overlap | Large enough for context, small enough for precise retrieval |
| Report format | Markdown | Renderable in Streamlit, downloadable, human-readable |
| Temperature | 0.0 | Deterministic outputs for reproducibility |
| Top-K retrieval | 5 | Enough context without overwhelming the prompt |
| Events per category in report | 5 | Ensures all categories are represented without hitting context limits |
| Target resource extraction | From requestParameters | Distinguishes actor (who did it) from target (what was done to) |
| Noise filtering | Predefined event name set | Removes routine AWS background activity that drowns real events |

---

## 14. Potential Interview Questions & Answers

**Q: Why not use a single agent instead of multiple?**
A: Separation of concerns. Each agent has a single responsibility, making the system easier to test, debug, and explain. Only the Report Synthesis agent performs deep reasoning — the most expensive and hallucination-prone step. By delaying it until all data is gathered and verified, we minimize hallucination risk.

**Q: Why not use the CloudTrail LookupEvents API instead of reading from S3?**
A: The LookupEvents API only covers the last 90 days and has rate limits. Reading from S3 gives full history access, better performance for bulk reads, and demonstrates a more realistic production pattern.

**Q: What happens if the LLM hallucinates in the report?**
A: The confidence gating mechanism mitigates this. The system only generates a report after verifying that sufficient documentation has been retrieved (confidence >= 0.50). If confidence is low, the report includes a visible disclaimer. Additionally, every recommendation in the report cites a specific documentation source, making hallucinations verifiable.

**Q: Why is the confidence threshold 0.50 and not higher?**
A: Titan Embeddings V2 produces lower cosine similarity scores than other embedding models. Through testing, we found that scores above 0.50 consistently returned relevant documentation, while scores below 0.50 returned poor matches. The threshold was calibrated empirically, not chosen arbitrarily.

**Q: How does the system handle vague queries like "anything suspicious"?**
A: The Event Filter (Step 3) asks Claude which categories are relevant. For vague queries, Claude returns all categories, so all events and documentation are included. The Report Synthesis agent then uses its judgment to focus on the most security-relevant findings.

**Q: Why use RAG if Claude already knows about AWS?**
A: Claude's training data may be outdated and can't be verified. RAG provides specific, citable documentation that makes the report audit-ready. An auditor can check "According to iam-best-practices.md..." against the actual document. You can't audit "According to Claude's training data..."

**Q: Why Pinecone instead of a local vector store like FAISS?**
A: Pinecone demonstrates real vector database usage — a managed, production-grade service. FAISS would work functionally but would be less impressive in a portfolio project and wouldn't demonstrate cloud-native patterns.

**Q: How does the system scale?**
A: Currently designed for single-account, single-region use. For scaling: multiple trails could be aggregated, the Pinecone index could be expanded with more documentation, and the Streamlit UI could be replaced with a production web framework. The pipeline architecture itself scales well because each agent is independent and stateless.

**Q: What's the latency of a typical query?**
A: Approximately 30-60 seconds. The bottleneck is the 4 Claude API calls through Bedrock. Potential optimizations: caching time parsing results, pre-computing event summaries, or parallelizing independent steps.

**Q: Why separate the Event Filter from Log Analysis?**
A: Log Analysis is about data collection — it gathers everything objectively. Event Filter is about question interpretation — it makes a subjective judgment about relevance. Keeping them separate means Log Analysis can be reused with different filtering strategies, and each step can be tested independently.
