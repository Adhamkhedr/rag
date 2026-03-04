# Project Report — DocuGen AI: Multi-Agent AWS Security Report Generator

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Business Context & Motivation](#2-business-context--motivation)
3. [System Architecture Overview](#3-system-architecture-overview)
4. [Technology Stack & Decision Rationale](#4-technology-stack--decision-rationale)
5. [Project Structure](#5-project-structure)
6. [Configuration & State Management](#6-configuration--state-management)
7. [The LangGraph Pipeline](#7-the-langgraph-pipeline)
8. [Agent Deep Dives](#8-agent-deep-dives)
9. [Service Layer](#9-service-layer)
10. [RAG System: Indexing & Retrieval](#10-rag-system-indexing--retrieval)
11. [Prompts & LLM Interaction Design](#11-prompts--llm-interaction-design)
12. [Streamlit UI](#12-streamlit-ui)
13. [Testing Strategy](#13-testing-strategy)
14. [End-to-End Data Flow](#14-end-to-end-data-flow)
15. [AWS Infrastructure](#15-aws-infrastructure)
16. [Performance Characteristics](#16-performance-characteristics)
17. [Security Considerations](#17-security-considerations)
18. [Limitations & Honest Assessment](#18-limitations--honest-assessment)
19. [Future Enhancements](#19-future-enhancements)

---

## 1. Executive Summary

DocuGen AI is an end-to-end multi-agent system that automatically generates **audit-ready security incident reports** from AWS CloudTrail logs. A user types a plain-English question — *"What IAM changes happened yesterday?"* — and within 30–60 seconds receives a structured Markdown report with a timeline of events, risk assessment, and recommended actions, every finding grounded in real AWS documentation retrieved via semantic search.

The system orchestrates **six specialized AI agents** through a LangGraph pipeline. It uses **Claude 3.5 Sonnet** (via Amazon Bedrock) as the reasoning engine, **Amazon Titan Embeddings V2** to encode documentation into vectors, **Pinecone** as the vector database, and **Amazon S3** both as the source of CloudTrail logs and as the destination for generated reports. The user interface is a **Streamlit** web app.

**Key Innovation**: Every report is documentation-grounded. Before writing a single sentence, the system retrieves the most semantically relevant chunks from 12 curated AWS documentation files (~100 pages) and hands them to Claude alongside the raw log events. The result is a report that does not just list events — it explains *why* they matter according to AWS's own security guidance, making it suitable for compliance audits, post-incident reviews, and security briefings.

**Architecture Highlight**: The pipeline includes a confidence-gated retry loop. If the vector similarity scores of retrieved documentation fall below a threshold, the retrieval agent automatically broadens its search query and tries again — up to three times — before proceeding with a disclaimer. This makes the system self-correcting rather than silently producing unreliable output.

---

## 2. Business Context & Motivation

### The Problem: CloudTrail Logs Are Unreadable at Human Scale

AWS CloudTrail records every API call made in an AWS account — who did what, when, from which IP, on which resource. On a typical active account, this generates hundreds to thousands of events per day across dozens of event types. When a security team needs to answer a question like *"Were there any unauthorized IAM changes last night?"*, the raw answer is buried in compressed JSON files spread across S3 folders, each event containing 50+ fields of AWS internals.

Traditionally, answering this question requires:

**1. Querying CloudTrail or Athena**
CloudTrail has a built-in search tool, but it is limited — basic filters only, 90-day history cap. For anything deeper, you need AWS Athena: a SQL query service that can search the raw log files in S3. This requires knowing SQL, knowing the exact table and column names AWS uses, and setting it up in advance. A non-technical person cannot do this.

**2. Writing filter expressions in an unfamiliar query syntax**
Even with SQL knowledge, CloudTrail's JSON structure is deeply nested. Filtering by username alone looks like:
```sql
WHERE json_extract(useridentity, '$.userName') = 'docugen-dev'
AND eventtime > '2026-02-07T00:00:00Z'
```
One wrong field name returns zero results with no explanation why.

**3. Interpreting raw JSON event fields**
Even after getting results, you are staring at raw JSON — 50+ fields per event, most of them irrelevant noise (`tlsDetails`, `requestID`, `principalId`, `eventVersion`, etc.). A non-technical person has no idea what matters and what to ignore.

**4. Manually cross-referencing AWS documentation to understand risk**
Say you see the event `AttachUserPolicy` — is that dangerous? You would need to open AWS documentation, look it up, understand what it does, and assess whether the specific policy attached represents a risk. That is extra time just to understand what you are looking at.

**5. Writing a report manually**
After all of that, you still have to write the report yourself — format it, assess the risk level, list recommendations. More hours of work.

This process takes hours, requires technical expertise, and is error-prone. It is also **reactive** — nobody goes through this pain unless something already went wrong: an alert fired, a breach was discovered, or a compliance audit demanded evidence. There is no proactive daily monitoring because the manual process is too costly.

### The Solution: Natural Language → Audit Report

DocuGen AI removes every manual step. A security analyst, cloud engineer, or even a compliance officer can type a plain-English question and receive a professional report. No query language, no JSON parsing, no manual documentation lookup.

### Why Grounding Reports in Documentation Matters

A report that says "user X created an IAM role" is a log dump. A report that says "user X created an IAM role granting full S3 access — per AWS IAM best practices (iam-best-practices.md), roles should follow least-privilege principles and be scoped to specific actions and resources" is an actionable security finding. The RAG component is what transforms the former into the latter. It is the difference between a log viewer and a security analyst.

### Why Audit-Ready Output Matters

Security teams operate under compliance frameworks (SOC 2, ISO 27001, PCI-DSS) that require documented evidence of security monitoring. A time-stamped, structured Markdown report stored in S3 with traceable metadata (which model was used, what confidence score was achieved, which documentation sources were referenced) is directly usable as audit evidence. This is not a chatbot — it is a documentation system.

### Who Uses This

| User | Use Case |
|---|---|
| Security Analyst | Investigate suspicious activity after an alert |
| Cloud Engineer | Routine audit of infrastructure changes |
| Compliance Officer | Generate evidence for audit cycles |
| DevOps Team | Quickly understand what happened during an incident |
| CISO | Review executive-level security summaries |

---

## 3. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER (Web Browser)                              │
│                           Streamlit Interface                               │
│                    "What IAM changes happened yesterday?"                   │
└─────────────────────────┬───────────────────────────────────────────────────┘
                          │ Plain English Query
                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        LangGraph Pipeline (graph.py)                        │
│                                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌─────────────┐ │
│  │  Agent 1     │   │  Agent 2     │   │  Agent 3     │   │  Agent 4    │ │
│  │ Time Parsing │──▶│ Log Analysis │──▶│ Event Filter │──▶│  Retrieval  │ │
│  │              │   │              │   │              │   │   + Retry   │ │
│  └──────────────┘   └──────────────┘   └──────────────┘   └──────┬──────┘ │
│                                                                    │        │
│                                                          ┌─────────▼──────┐ │
│                                                          │ Confidence     │ │
│                                                          │ Check          │ │
│                                                          │ (conditional   │ │
│                                                          │  edge)         │ │
│                                                          └────┬──────┬───┘ │
│                                                    "retry"    │      │     │
│                                                     ◀─────────┘      │     │
│                                                                "sufficient" │
│                                                                       │     │
│  ┌──────────────┐   ┌──────────────┐                                  │     │
│  │  Agent 6     │◀──│  Agent 5     │◀──────────────────────────────────┘     │
│  │ Store Report │   │   Report     │                                         │
│  │  (S3)        │   │  Synthesis   │                                         │
│  └──────────────┘   └──────────────┘                                         │
└─────────────────────────────────────────────────────────────────────────────┘
          │                                        ▲
          │                                        │
          ▼                                        │
┌─────────────────┐   ┌──────────────┐   ┌────────────────┐
│  Amazon S3      │   │  Amazon      │   │   Pinecone     │
│  (CloudTrail    │   │  Bedrock     │   │  Vector DB     │
│   Logs +        │   │  Claude 3.5  │   │  AWS Docs      │
│   Reports)      │   │  Sonnet +    │   │  ~200 vectors  │
│                 │   │  Titan V2    │   │                │
└─────────────────┘   └──────────────┘   └────────────────┘
```

The architecture follows a **linear agent pipeline with one conditional loop**. State is shared across all agents via a typed dictionary (`DocuGenState`). Each agent reads from shared state, does its work, and writes its outputs back to state. LangGraph manages the state transitions automatically.

---

## 4. Technology Stack & Decision Rationale

### LLM: Claude 3.5 Sonnet via Amazon Bedrock

**Why Claude 3.5 Sonnet?**
Claude 3.5 Sonnet is Anthropic's best mid-tier model — high instruction-following ability, strong structured output (JSON), and excellent long-context reasoning. For this project, it needs to: (1) parse time expressions precisely, (2) summarize raw CloudTrail events coherently, (3) decide which event categories are relevant to a question, and (4) write a professional multi-section Markdown report grounded in retrieved documentation. Claude 3.5 Sonnet handles all four reliably.

**Why Bedrock instead of the direct Anthropic API?**
Using Bedrock keeps the entire stack AWS-native. There is no separate API key for the LLM — the same AWS credentials used for S3 and CloudTrail are used for Bedrock. This means a single IAM policy governs all service access. It also means the solution can run entirely inside a VPC without outbound internet connectivity (via PrivateLink), which matters for enterprise deployments.

**Why the Converse API (not invoke_model)?**
Bedrock offers two ways to call models: `invoke_model` (raw JSON, model-specific format) and `converse` (standardized chat format). The Converse API provides a unified interface across all Bedrock chat models. If the underlying model is swapped (e.g., from Claude 3.5 Sonnet to Claude 3 Haiku for cost reduction), zero code changes are needed. This is the correct long-term pattern.

---

### Embeddings: Amazon Titan Embeddings V2

**Why Titan Embeddings instead of OpenAI or Cohere?**
Titan Embeddings V2 is available through Bedrock, requiring no additional credentials or third-party accounts. It produces 1024-dimensional vectors with strong semantic representation for technical documentation. Keeping embeddings AWS-native also means a consistent security posture: no customer data ever leaves AWS infrastructure.

**Why normalize=True?**
Titan V2 returns raw vectors whose magnitude varies with text length. Without normalization, a longer text appears "more similar" to a query simply because its vector is larger — not because it is semantically closer. Setting `normalize=True` scales every vector to unit length (magnitude = 1), ensuring that cosine similarity measures only semantic angle, not size. This is required for meaningful similarity comparisons.

**Why 1024 dimensions?**
Titan V2's native output is 1024 dimensions. Using the full dimensionality preserves the maximum amount of semantic information. The Pinecone index must be configured to exactly 1024 dimensions at creation time — this cannot be changed after creation.

---

### Vector Database: Pinecone

**Why Pinecone over FAISS or Weaviate?**
FAISS is an excellent local vector library but it stores vectors in memory on a single machine — not suitable for a cloud-native architecture and adds no portfolio value. Pinecone is a managed cloud vector database with a generous free tier capable of storing the ~200 vectors this project generates. It demonstrates real vector database usage (not a local approximation), is accessible from any machine without setup, and requires zero infrastructure maintenance.

**Index Configuration**:
- Dimensions: 1024 (must match Titan V2)
- Metric: cosine (semantic similarity, not Euclidean)
- Single namespace (project scope is one documentation set)

**Why cosine similarity?**
Cosine similarity measures the angle between two vectors — it captures semantic direction regardless of text length. A short query like "IAM roles best practices" will match a long documentation paragraph because they point in the same semantic direction, even though their vector magnitudes differ. Euclidean distance would penalize length differences irrelevant to meaning.

---

### Pipeline Orchestration: LangGraph

**Why LangGraph over plain function calls?**
The critical requirement that pushed the decision toward LangGraph is the **conditional retry loop in retrieval**. After each retrieval attempt, the pipeline must evaluate confidence and either proceed to report generation or loop back to retrieval with a broader query. Expressing this with plain function calls requires manually written if/else logic and manual state passing between functions. LangGraph expresses this as a declarative graph with a conditional edge — the intent is clear, the state management is automatic, and the structure is visualizable.

LangGraph also provides:
- **Automatic state merging**: Each agent returns a dict of updates; LangGraph merges it into shared state
- **Industry credibility**: LangGraph is the dominant framework for production LLM agents, making this architecture pattern directly transferable to professional work
- **Graph visualization**: The pipeline can be rendered as a diagram for documentation

---

### UI: Streamlit

**Why Streamlit?**
The primary user is technical — a security analyst or cloud engineer. The priority is functionality: submit a query, see a professional report, download it. Streamlit delivers this in ~50 lines of Python with no HTML, CSS, or JavaScript. Built-in components (spinners, download buttons, `st.markdown()`) cover every UI need. The choice optimizes for speed-to-working-product over custom UI flexibility.

---

## 5. Project Structure

```
Agents(2)/
├── .env                        # Secrets (API keys, AWS credentials) — gitignored
├── .env.example                # Template showing required environment variables
├── requirements.txt            # All Python dependencies with pinned versions
├── config.py                   # Single source of truth for all settings
├── state.py                    # TypedDict definitions for shared pipeline state
├── graph.py                    # LangGraph pipeline: nodes, edges, conditional logic
├── app.py                      # Streamlit web interface (entry point)
│
├── agents/                     # Six specialized agents (one responsibility each)
│   ├── time_parsing.py         # Agent 1: Natural language → ISO-8601 timestamps
│   ├── log_analysis.py         # Agents 2 & 3: CloudTrail download, filter, categorize
│   ├── retrieval.py            # Agent 4: RAG semantic search + confidence scoring
│   └── report_synthesis.py     # Agents 5 & 6: Report generation + S3 storage
│
├── services/                   # External service wrappers (one per service)
│   ├── bedrock_llm.py          # Claude 3.5 Sonnet via Bedrock Converse API
│   ├── bedrock_embeddings.py   # Titan Embeddings V2 via Bedrock invoke_model
│   ├── pinecone_client.py      # Pinecone vector DB (upsert, query, stats)
│   ├── s3_client.py            # S3: CloudTrail log reading + report writing
│   └── indexer.py              # First-run document indexing (runs once)
│
├── docs/aws/                   # Curated AWS documentation (~12 files, ~100 pages)
│   ├── iam-users-guide.md
│   ├── iam-roles-guide.md
│   ├── iam-policies-guide.md
│   ├── iam-best-practices.md
│   ├── aws-security-fundamentals.md
│   ├── cloudtrail-overview.md
│   ├── cloudtrail-log-format.md
│   ├── ec2-instances-guide.md
│   ├── ec2-security-groups.md
│   ├── s3-buckets-guide.md
│   ├── s3-access-control.md
│   └── lambda-overview.md
│
└── tests/                      # Pytest test suite
    ├── conftest.py             # Fixtures and mocks (all external services mocked)
    ├── test_time_parsing.py
    ├── test_log_analysis.py
    ├── test_retrieval.py
    ├── test_report_synthesis.py
    └── test_graph.py           # Full integration test
```

**Design principle**: Each file has a single, clear responsibility. The agents directory contains business logic; the services directory contains external API wrappers; the graph connects them. This separation means services can be replaced (e.g., swap Pinecone for Weaviate) without touching any agent code.

---

## 6. Configuration & State Management

### config.py — The Single Source of Truth

Every tunable parameter lives in one file. If a threshold needs adjustment, it is changed in one place and propagates everywhere:

| Setting | Value | Why This Value |
|---|---|---|
| `CLAUDE_MODEL_ID` | `us.anthropic.claude-3-5-sonnet-20241022-v2:0` | Best Sonnet model available, cross-region inference enabled |
| `TITAN_EMBED_MODEL_ID` | `amazon.titan-embed-text-v2:0` | V2 produces 1024-dim vectors, higher quality than V1 |
| `EMBEDDING_DIMENSION` | 1024 | Titan V2's native output; Pinecone index must match exactly |
| `CONFIDENCE_THRESHOLD` | 0.50 | Calibrated empirically — Titan V2 scores tend to cluster 0.45–0.75 |
| `MAX_RETRIES` | 2 | 3 total attempts (initial + 2 retries) balances quality vs. latency |
| `CHUNK_SIZE` | 1000 characters | ~200 words — one focused topic per chunk, good retrieval precision |
| `CHUNK_OVERLAP` | 200 characters | Preserves sentences spanning chunk boundaries |
| `TOP_K` | 5 | 5 retrieved chunks provide enough context without overloading the prompt |

**Why CONFIDENCE_THRESHOLD = 0.50 and not 0.75?**

Titan Embeddings V2 operates on a different similarity scale than models like OpenAI's text-embedding-ada-002. Empirically, a score of 0.65 with Titan V2 represents a very good semantic match — equivalent to what might score 0.88 with ada-002. Setting the threshold at 0.75 would cause false failures (the retrieval would retry even when it had found genuinely relevant documentation). The 0.50 threshold was calibrated by running actual queries and observing the score distribution for good vs. poor matches.

### state.py — Typed Pipeline State

`DocuGenState` is a `TypedDict` — Python's typed dictionary — that defines the shared data structure flowing through all six agents:

```
DocuGenState:
  query:                str                    # User's original question
  time_range:           Optional[TimeRange]    # Populated by Agent 1
  log_findings:         Optional[LogFindings]  # Populated by Agent 2
  relevant_categories:  Optional[list[str]]    # Populated by Agent 3
  retrieved_docs:       Optional[list[...]]    # Populated by Agent 4
  retrieval_confidence: float                  # Populated by Agent 4
  retry_count:          int                    # Managed by graph retry logic
  final_report:         Optional[str]          # Populated by Agent 5
  metadata:             Optional[ReportMetadata]  # Populated by Agent 6
```

**Why TypedDict?**
TypedDict provides static type checking (IDE autocompletion, mypy validation) without the overhead of a full dataclass. LangGraph requires a typed state class — TypedDict is the idiomatic choice. Every agent knows exactly what fields exist, what their types are, and whether they may be None at a given pipeline stage.

**LogEvent — the simplified event structure:**
CloudTrail events contain 50+ fields (request parameters, response elements, TLS details, etc.). For security analysis and report generation, only 7 fields matter:

```
eventTime       → WHEN
eventName       → WHAT action (e.g., CreateUser)
userName        → WHO
sourceIP        → FROM WHERE
region          → WHERE in AWS
category        → TYPE (IAM_CHANGE, AUTH_EVENT, etc.)
targetResource  → ON WHAT (e.g., the new user's name)
```

This reduction from 50+ to 7 fields is a deliberate design decision — it keeps prompts small (reducing token cost and improving LLM focus) and makes the data interpretable by the report agent.

---

## 7. The LangGraph Pipeline

### Graph Construction (graph.py)

The pipeline is defined declaratively in `build_graph()`:

```
Nodes registered:
  time_parsing        → time_parsing_node()
  log_analysis        → log_analysis_node()
  event_filter        → event_filter_node()
  retrieval           → retrieval_node()
  confidence_check    → (conditional edge target)
  increment_retry     → increment_retry_node()
  report_synthesis    → report_synthesis_node()
  store_report        → store_report_node()

Edges:
  START               → time_parsing
  time_parsing        → log_analysis
  log_analysis        → event_filter
  event_filter        → retrieval
  retrieval           → confidence_check  (conditional edge)
    "retry"           → increment_retry
    "sufficient"      → report_synthesis
  increment_retry     → retrieval         (loop back)
  report_synthesis    → store_report
  store_report        → END
```

### The Confidence Retry Loop

This is the architectural heart of the pipeline. After every retrieval attempt, `confidence_check()` evaluates the average cosine similarity of the 5 retrieved documents:

```
if avg_similarity >= 0.50:
    → proceed to report_synthesis ("sufficient")
elif retry_count < 2:
    → increment_retry → retrieval ("retry")
else:
    → proceed anyway with disclaimer ("sufficient")
```

The third case (retries exhausted) is crucial — the system never fails silently. It proceeds to report generation but embeds a warning in the prompt so Claude explicitly includes a disclaimer in the report: *"Retrieval confidence is below threshold; recommendations may not be fully grounded in documentation."* The user always gets a report, but the report's reliability is transparently communicated.

**Why not just fail if confidence is low?**
A low confidence score means the documentation didn't have a perfectly matching chunk — it does not mean the events are unanalyzable. The CloudTrail events themselves are factual. Even with limited documentation grounding, Claude can still produce a factually accurate timeline and risk assessment from the raw events. The disclaimer accurately communicates the limitation without blocking the user.

### First-Run Indexing

Before the graph runs any pipeline node, `build_graph()` calls `index_documents()`. This checks if Pinecone already has data:
- **First run**: Indexes all 12 documentation files (~200 chunks). Takes ~1–2 minutes.
- **All subsequent runs**: Detects existing data, skips entirely. Takes ~1 second.

This means the system "warms up" once and is fast forever after.

---

## 8. Agent Deep Dives

### Agent 1: Time Parsing

**File**: `agents/time_parsing.py`
**Input**: `state["query"]` — the raw user question
**Output**: `state["time_range"]` — `{"start": "YYYY-MM-DDT00:00:00Z", "end": "YYYY-MM-DDT23:59:59Z"}`

**The Problem**: CloudTrail logs are organized by date in S3 (`YYYY/MM/DD/` prefix structure). To know which files to download, the pipeline must convert a human phrase like "yesterday" into precise ISO-8601 timestamps before any S3 calls are made.

**The Solution**: Claude is given the exact current UTC time and asked to parse the time expression. Temperature is set to 0.0 — this task is deterministic, not creative. Max tokens is set to 200 — the response is a small JSON object, never a long text.

**Why inject current UTC time into the prompt?**
Relative expressions like "yesterday," "last Tuesday," or "this morning" have no meaning without a reference point. Without the current time, Claude would either hallucinate a date or refuse to answer. The prompt injects `datetime.now(timezone.utc).isoformat()` at call time so every invocation has a precise anchor.

**Handling LLM quirks**: Claude occasionally wraps JSON responses in markdown code fences (` ```json ... ``` `). The agent strips these before parsing, making it robust to minor formatting variations.

---

### Agent 2: Log Analysis

**File**: `agents/log_analysis.py`
**Input**: `state["time_range"]`
**Output**: `state["log_findings"]` — `{events: [...], summary: "..."}`

This is the most computationally intensive agent. It performs seven sequential phases:

**Phase 1: Build S3 paths**
Converts ISO-8601 timestamps to a list of calendar dates (handling multi-day ranges). For each date, builds the S3 prefix: `AWSLogs/{account_id}/CloudTrail/{region}/YYYY/MM/DD/`.

**Phase 2: List files**
Uses an S3 paginator (not a simple list call) because a busy account can generate >1000 log files per day, exceeding the 1000-item S3 list limit. A paginator automatically handles continuation tokens. Files are pre-filtered at this stage by parsing timestamps from filenames using a regex (`T\d{4}Z` pattern) — files clearly outside the time range are never downloaded.

**Phase 3: Download and decompress**
CloudTrail logs are stored as `.json.gz` (gzip-compressed JSON). Each file is downloaded from S3 and decompressed in memory. The resulting JSON contains a `Records` array of raw events.

**Phase 4: Exact timestamp filtering**
File-level filtering is approximate (CloudTrail files often contain a few hours of events, and file timestamps are not event timestamps). This phase re-filters at the individual event level, keeping only events whose `eventTime` falls within the requested range.

**Phase 5: Simplify and categorize**
Reduces each CloudTrail event from 50+ fields to 7. Categorization is done by **dictionary lookup** (not LLM) — the mapping from event names to categories is fixed and well-defined:

| Category | Example Events |
|---|---|
| `IAM_CHANGE` | CreateUser, DeleteUser, AttachUserPolicy, CreateRole, CreateAccessKey |
| `AUTH_EVENT` | ConsoleLogin, GetSessionToken, AssumeRole |
| `SECURITY_GROUP` | AuthorizeSecurityGroupIngress, CreateSecurityGroup |
| `S3_CONFIG` | CreateBucket, PutBucketPolicy, PutBucketAcl |
| `EC2_LIFECYCLE` | RunInstances, TerminateInstances, StopInstances |
| `CLOUDTRAIL_CONFIG` | CreateTrail, StopLogging, DeleteTrail |
| `OTHER` | Anything not in the above lists |

**Why deterministic categorization instead of LLM?**
The mapping is exhaustive and well-defined. There is no ambiguity — `CreateUser` is always an IAM change. Using an LLM here would add 2–3 seconds of latency and introduce the possibility of misclassification. Deterministic code is faster, cheaper, and more reliable for a finite, well-understood problem.

**Phase 6: Noise separation**
On a typical AWS account, ~95% of CloudTrail events are routine service-to-service calls: `GetBucketAcl`, `ListBuckets`, `GenerateDataKey`, `HeadBucket`, `LookupEvents`, etc. These are not deleted — they are moved to the end of the events list. A typical day: ~20–50 security-relevant events + ~800+ noise events. The report focuses on the relevant events; the noise is preserved for full audit trail completeness.

**Phase 7: Generate summary**
Sends up to 50 security-relevant events to Claude with a request for a 2–3 sentence summary. This summary accompanies the full event list throughout the rest of the pipeline, giving subsequent agents a quick overview without re-reading all events.

---

### Agent 3: Event Filter

**File**: `agents/log_analysis.py` (same file, separate function)
**Input**: `state["query"]`, `state["log_findings"]["events"]`
**Output**: `state["relevant_categories"]` — list of category names

**Purpose**: Not every category of events is relevant to every question. If the user asks *"What security group changes happened today?"*, sending IAM events, S3 events, and EC2 lifecycle events to the retrieval and report steps is noise that reduces focus and wastes tokens.

**How it works**: Claude is given the user's question and the list of categories found in the events. It returns a comma-separated list of relevant categories. A fail-safe handles the edge case where Claude returns nothing: all categories are kept.

**Design Choices Considered**:

| Option | Mechanism | Chosen? |
|---|---|---|
| A: Send everything | No filtering | No — unfocused RAG, wastes tokens |
| B: LLM filter | Claude decides relevance | **Yes** — most precise |
| C: Query-biased ranking | Adjust Pinecone scores | No — biases but doesn't exclude |

Option B was chosen for precision. The cost is ~100 tokens and ~2–3 seconds — acceptable for the quality gain. For a broad question ("What happened today?"), Claude correctly returns all categories.

---

### Agent 4: Retrieval with Confidence-Gated Retry

**File**: `agents/retrieval.py`
**Input**: Filtered events, relevant categories, retry count
**Output**: `state["retrieved_docs"]`, `state["retrieval_confidence"]`

**The Retrieval Query Construction**:
Rather than embedding the raw user question, the agent constructs a purpose-built retrieval query tailored to the event categories. This is more precise because the user's question ("What IAM changes happened yesterday?") is optimized for human communication, not semantic vector matching. A purpose-built query ("IAM users roles policies best practices least privilege credentials") is optimized for matching documentation content.

**Retry Strategy — Progressively Broadening Queries**:

| Attempt | Query Strategy | Example |
|---|---|---|
| 0 (first) | Category-specific technical terms | `"IAM users roles policies best practices least privilege credentials"` |
| 1 (second) | Broader AWS security context | `"AWS security best practices shared responsibility model monitoring access control"` |
| 2 (third) | Broadest possible | `"AWS cloud security IAM identity access management incident response compliance"` |

**Confidence Calculation**: After retrieving the top 5 Pinecone results, confidence is computed as the arithmetic mean of their cosine similarity scores:

```
confidence = (sim_1 + sim_2 + sim_3 + sim_4 + sim_5) / 5
```

This is deliberate — averaging forces all 5 results to be relevant, not just the top 1. A single excellent match surrounded by poor matches would not meet the threshold, correctly triggering a retry.

---

### Agent 5: Report Synthesis

**File**: `agents/report_synthesis.py`
**Input**: Query, time range, filtered events, summary, retrieved docs, confidence
**Output**: `state["final_report"]` — complete Markdown report

**Event Balancing Strategy**:
To ensure the report covers all relevant event types proportionally, the agent groups events by category and takes up to 5 events per category. This prevents a report dominated by one category (e.g., 10 IAM events overshadowing 2 security group events) when the user asked about both.

**Low-Confidence Handling**:
The confidence score is passed explicitly into the report generation prompt. Claude's instructions differ based on it:
- **Confidence ≥ 0.50**: Write a confident report citing documentation sources. Do not include warnings.
- **Confidence < 0.50**: Include a prominent disclaimer at the top: documentation grounding was limited; the timeline is factual but recommendations may be incomplete.

This is a key design principle: *the system never lies about its reliability*. The report transparently communicates what it knows vs. what it inferred.

**Report Structure** (enforced via system prompt):
```
# Incident Report
## Executive Summary
## Time Range Analyzed
## Timeline of Events (table: Time | Event | User | Source IP | Category)
## Detailed Findings (references AWS documentation)
## Risk Assessment (Low / Medium / High with justification)
## Recommended Actions (numbered list)
## Grounding & Confidence (score + documentation sources cited)
```

---

### Agent 6: Store Report

**File**: `agents/report_synthesis.py` (same file, separate function)
**Input**: Final report Markdown, metadata
**Output**: S3 upload confirmation

Two files are written to S3 per report:
```
s3://docugen-reports-{account_id}/reports/YYYY-MM-DD/{report_id}-report.md
s3://docugen-reports-{account_id}/reports/YYYY-MM-DD/{report_id}-metadata.json
```

The metadata JSON contains:
```json
{
  "report_id": "a1b2c3d4",
  "query": "What IAM changes happened yesterday?",
  "time_range": {"start": "...", "end": "..."},
  "generated_at": "2026-02-08T15:30:00Z",
  "model_used": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
  "retrieval_confidence": 0.72,
  "sources_referenced": ["iam-users-guide.md", "iam-best-practices.md"],
  "event_count": 42
}
```

**Why store both report and metadata separately?**
The Markdown file is for human consumption — security analysts read it. The JSON metadata file is for programmatic consumption — audit systems can query it, dashboards can aggregate confidence scores over time, and compliance tools can verify that specific documentation was referenced in each report.

---

## 9. Service Layer

All five service files follow the same **singleton pattern**:

```python
_client = None

def get_client():
    global _client
    if _client is None:
        _client = boto3.client(...)
    return _client
```

**Why singleton?** Creating a new AWS boto3 client or Pinecone connection for every API call involves authentication overhead, TCP handshake setup, and object initialization. With 6 agents making multiple API calls each, this would add several seconds of unnecessary overhead per pipeline run. The singleton creates the connection once on first use and reuses it for the lifetime of the Streamlit session.

### bedrock_llm.py

Wraps Claude 3.5 Sonnet via the Converse API. The core function:

```
invoke_claude(system_prompt, user_message, max_tokens) → str
```

Response extraction path: `response["output"]["message"]["content"][0]["text"]`

Temperature is always 0.0 — every Claude call in this pipeline has a deterministic, structured task. There is no benefit to randomness in time parsing, event categorization, or report writing.

Used by all four LLM-dependent agents with different `max_tokens` values:
- Time parsing: 200 tokens (small JSON response)
- Log summary: 300 tokens (2–3 sentences)
- Event filter: 100 tokens (comma-separated category names)
- Report synthesis: 4096 tokens (full multi-section report)

### bedrock_embeddings.py

Wraps Titan Embeddings V2 via the lower-level `invoke_model()` API.

**Why invoke_model() instead of converse()?**
Converse is a chat API designed for models that generate text responses. Titan Embeddings is not a chat model — it takes text in and returns a vector of 1024 floating-point numbers. It has no concept of conversation turns. `invoke_model()` is the general Bedrock API that passes raw JSON and receives raw JSON, which is what embedding models require.

**embed_text()** vs **embed_texts()**:
- `embed_text()`: Single embedding, used per-query during retrieval
- `embed_texts()`: Sequential embeddings for a list of texts, used during first-run indexing
- Note: Titan V2 does not support batch embedding in a single API call, so `embed_texts()` loops sequentially

### pinecone_client.py

Three primary operations:

**upsert_vectors()**: Uploads document chunk vectors during indexing. Batches into groups of 100 per request (Pinecone's recommended batch size). Each vector carries metadata: the original text chunk and its source filename. This metadata is stored in Pinecone alongside the vector, so when retrieved, the original text is immediately available without re-reading files.

**query_vectors()**: Semantic search. Sends the query embedding, receives the top-K most similar document chunks with their similarity scores and metadata.

**index_has_data()**: Returns True if the vector count is > 0. Used to skip re-indexing on every app startup. Critical for keeping startup time under 5 seconds after the first run.

### s3_client.py

**list_cloudtrail_files()**: Two-level filtering:
1. File-level: Build S3 prefixes for each day in the range, list files, filter by timestamp extracted from filename (e.g., `20260208T1100Z` → 11:00 AM on Feb 8)
2. Event-level: Done downstream in log_analysis.py — each event's timestamp is checked individually

Uses S3 paginator for >1000 files (large accounts can generate thousands of log files per day).

**read_cloudtrail_file()**: Downloads a `.json.gz` file, decompresses with Python's `gzip` module, parses JSON, returns the `Records` array.

**store_report()**: Writes two objects to S3 with appropriate Content-Type headers (`text/markdown` and `application/json`).

---

## 10. RAG System: Indexing & Retrieval

### What is RAG?

Retrieval-Augmented Generation (RAG) is the technique of supplementing an LLM's context window with relevant information retrieved at query time from an external knowledge base. Instead of relying on Claude's training data knowledge (which may be outdated, general, or hallucinated), the pipeline retrieves specific text chunks from trusted documentation and includes them in the prompt. Claude's report is then grounded in these exact sources.

### Why RAG for This Project?

AWS security best practices evolve. IAM policies change. New CloudTrail event types are added. A purely knowledge-based LLM might cite outdated guidance. By indexing curated, up-to-date AWS documentation and retrieving it at query time, the reports cite current and verifiable sources — exactly what compliance audits require.

### Indexing Pipeline (indexer.py)

Runs exactly once (first startup, ~1–2 minutes):

```
For each of 12 AWS documentation files:
  1. Read full Markdown content
  2. Split into chunks using RecursiveCharacterTextSplitter
     - chunk_size: 1000 chars (~200 words)
     - chunk_overlap: 200 chars
  3. For each chunk:
     - Embed with Titan V2 → 1024-dim vector
     - Create Pinecone vector:
         id: "iam-users-guide.md::chunk-3"
         values: [1024 floats]
         metadata: {content: "...", source: "iam-users-guide.md", chunk_index: 3}
  4. Batch upload to Pinecone (100 vectors/batch)
```

**Why chunk at 1000 characters?**
A full document embedding represents the "average meaning" of the entire document — too vague for precise retrieval. A chunk of ~200 words covers one focused topic (e.g., "IAM least privilege" or "S3 bucket policies") and produces a vector that represents that specific topic. The retrieval query can then match this focused meaning.

**Why 200-character overlap?**
Sentences often span chunk boundaries. Without overlap, a key sentence might be split across two chunks and partially lost in each. The 200-character overlap ensures that sentences at boundaries appear in full in at least one chunk. Example:
- Chunk 0: characters 0–999
- Chunk 1: characters 800–1799
- Chunk 2: characters 1600–2599

### Retrieval at Query Time

1. Agent 4 builds a category-specific retrieval query string
2. Titan V2 embeds this string → 1024-dim query vector
3. Pinecone finds the 5 most similar document vectors (cosine similarity)
4. Returns: 5 `{content, source, similarity}` dicts
5. Average similarity = confidence score
6. If confidence ≥ 0.50, proceed; else retry with broader query

The retrieved chunks' `content` fields (original text) are then included in the report synthesis prompt, so Claude can cite and build upon them.

---

## 11. Prompts & LLM Interaction Design

### Time Parsing Prompt

```
System: You are a time parsing assistant. Convert the user's time expression to
        ISO-8601 UTC timestamps. Return ONLY valid JSON. No explanation, no markdown.

User:   [Current UTC time injected] + user's question

Output: {"start": "2026-02-06T00:00:00Z", "end": "2026-02-06T23:59:59Z"}
```

Key design choices:
- "Return ONLY valid JSON" prevents prose explanations
- Current UTC time injected to enable relative expressions
- Max tokens = 200 (bounds cost, prevents hallucination padding)
- Temperature = 0.0 (deterministic)

### Log Summary Prompt

```
System: You are a concise AWS security log analyst. Summarize briefly.

User:   Summarize these {count} CloudTrail events in 2-3 sentences.
        Total: {significant} security-relevant, {noise} routine calls filtered out.
        User's question: {query}
        Events: {json_events (up to 50)}
```

The user's original question is included so the summary is query-aware — a summary for "what IAM changes happened?" focuses on IAM; for "any unusual logins?" focuses on auth events.

### Event Filter Prompt

```
System: You select relevant event categories. Respond with only category names
        separated by commas.

User:   The user asked: "{query}"
        Categories found: {categories}
        Category descriptions: [list]

        If the question is broad ("what happened today"), return ALL categories.
        Respond with ONLY category names separated by commas. Nothing else.
```

The "broad question" instruction is critical — without it, Claude might filter categories from a general query, causing valid events to be missed.

### Report Synthesis Prompt

This is the most complex prompt in the system. Key elements:

1. **Role definition**: "You are an expert AWS security analyst generating an audit-ready incident report"
2. **Grounding rules**: "Ground every finding in the provided CloudTrail events and AWS documentation. Reference specific event names, timestamps, users. Cite documentation sources by filename."
3. **Conditional confidence instruction**:
   - High confidence: "Do NOT include warnings. Write a confident, authoritative report."
   - Low confidence: "Include a prominent WARNING at the top about limited documentation grounding."
4. **Strict report structure**: The exact section headers are specified to guarantee consistent output format, enabling downstream processing.

---

## 12. Streamlit UI

**File**: `app.py` (47 lines)

The UI is intentionally minimal:

1. **Text input**: Single field with placeholder "e.g., What IAM changes happened yesterday?"
2. **Spinner**: Displayed during pipeline execution ("Analyzing CloudTrail logs and generating report...")
3. **Report rendering**: `st.markdown()` renders the report with full formatting (headers, tables, bold text)
4. **Confidence indicator**:
   - Green check (✓): Confidence ≥ 0.50
   - Yellow warning (⚠️): Confidence < 0.50
5. **Metadata panel**: Collapsible JSON display (`st.expander`)
6. **Download button**: `st.download_button()` for the raw Markdown file
7. **Error handling**: `try/except` wraps the pipeline call; exceptions display a user-friendly error message

**Why not a more sophisticated UI?**
The primary deliverable is the report, not the interface. A security analyst's workflow is: ask question → read report → download for records. Streamlit's built-in Markdown rendering, download buttons, and spinners cover this workflow completely in 47 lines of code.

---

## 13. Testing Strategy

### Philosophy: Mock All External Services

Every external API call (Bedrock, S3, Pinecone) is mocked in tests. This achieves:
- **Speed**: Tests run in seconds, not minutes
- **Cost**: No AWS API charges during CI/CD
- **Reliability**: Tests pass regardless of AWS account state
- **Isolation**: A test failure means the code is wrong, not the network

### Fixture Design (conftest.py)

**mock_invoke_claude**: A sequential mock that returns different responses based on call order:
- Call 1 (time parsing): `{"start": "2026-02-06T00:00:00Z", "end": "2026-02-06T23:59:59Z"}`
- Call 2 (log summary): `"3 IAM changes detected, including user creation"`
- Call 3 (event filter): `"IAM_CHANGE"`
- Call 4 (report synthesis): Full Markdown report

This design mirrors the actual pipeline call order without requiring actual API calls.

**mock_embed_text**: Returns `[0.1] * 1024` — a deterministic unit vector. All similarity scores become identical (1.0 since all vectors are the same), which keeps confidence math predictable in tests.

### Test Coverage

**test_time_parsing.py** (3 tests):
- Returns valid TimeRange dict
- Strips markdown code fences from Claude's response
- Passes the full query to Claude

**test_log_analysis.py** (7 tests):
- Correct categorization for each of the 6 categories
- Unknown events → "OTHER"
- Full category mapping coverage

**test_retrieval.py** (5 tests):
- Confidence ≥ 0.50 → returns "sufficient"
- Confidence < 0.50 + retries available → returns "retry"
- Retries exhausted → returns "sufficient" (graceful degradation)
- Query broadens on each retry attempt (Retry 0 ≠ Retry 1 ≠ Retry 2)

**test_report_synthesis.py** (2 tests):
- Returns both `final_report` and `metadata` fields
- Low confidence inserts "WARNING" into the synthesis prompt

**test_graph.py** (1 integration test):
- Runs the full LangGraph pipeline end-to-end with all services mocked
- Verifies `final_report` exists and contains "Incident Report"
- Verifies `metadata.event_count` matches input
- Verifies `retrieval_confidence` is correctly calculated

---

## 14. End-to-End Data Flow

The following traces a complete request from user input to final report:

```
User: "What IAM changes happened yesterday?"
  │
  ▼ Agent 1: Time Parsing
  │   - Current UTC: 2026-02-08T12:00:00Z
  │   - Claude interprets "yesterday" → full day Feb 7
  │   - Output: {"start": "2026-02-07T00:00:00Z", "end": "2026-02-07T23:59:59Z"}
  │
  ▼ Agent 2: Log Analysis
  │   - Builds S3 prefix: AWSLogs/.../2026/02/07/
  │   - Lists 3 .json.gz files, downloads and decompresses
  │   - Parses 850 raw CloudTrail events
  │   - Filters to events in the exact timestamp range: 812 events
  │   - Reduces to 7 fields, categorizes: 38 IAM_CHANGE, 12 AUTH_EVENT, 800 noise
  │   - Sends 50 relevant events to Claude for summary
  │   - Output: LogFindings{events: [50 events], summary: "38 IAM changes..."}
  │
  ▼ Agent 3: Event Filter
  │   - Query: "What IAM changes happened yesterday?"
  │   - Categories found: [IAM_CHANGE, AUTH_EVENT]
  │   - Claude returns: "IAM_CHANGE"
  │   - Filters events to IAM_CHANGE only: 38 events
  │   - Output: relevant_categories = ["IAM_CHANGE"]
  │
  ▼ Agent 4: Retrieval (Attempt 1)
  │   - Builds query: "IAM users roles policies best practices least privilege credentials"
  │   - Titan V2 embeds query → 1024-dim vector
  │   - Pinecone search: top 5 most similar chunks
  │   - Results:
  │     {source: "iam-best-practices.md", similarity: 0.82}
  │     {source: "iam-users-guide.md",    similarity: 0.79}
  │     {source: "iam-policies-guide.md", similarity: 0.71}
  │     {source: "iam-roles-guide.md",    similarity: 0.68}
  │     {source: "aws-security-fundamentals.md", similarity: 0.61}
  │   - Confidence = (0.82+0.79+0.71+0.68+0.61)/5 = 0.722
  │   - 0.722 ≥ 0.50 → "sufficient" → proceed
  │
  ▼ Agent 5: Report Synthesis
  │   - Selects up to 5 IAM_CHANGE events
  │   - Builds prompt with: query, time range, 5 events, summary, 5 doc chunks
  │   - Claude writes full Markdown report:
  │     - Executive Summary
  │     - Timeline (table with timestamps and users)
  │     - Findings (cites iam-best-practices.md)
  │     - Risk Assessment: MEDIUM
  │     - Actions: 4 numbered recommendations
  │     - Grounding: confidence 0.722, sources listed
  │   - Output: final_report (Markdown string, ~2KB)
  │
  ▼ Agent 6: Store Report
  │   - report_id = "a1b2c3d4"
  │   - S3 upload: reports/2026-02-07/a1b2c3d4-report.md
  │   - S3 upload: reports/2026-02-07/a1b2c3d4-metadata.json
  │
  ▼ Streamlit UI
      - Renders Markdown report
      - Shows green confidence indicator (0.722 ≥ 0.50)
      - Shows collapsible metadata JSON
      - Shows download button → user saves report
```

Total time: ~35–45 seconds

---

## 15. AWS Infrastructure

### AWS CloudTrail

AWS CloudTrail is the native AWS service that logs every API call made in an account. It records: who made the call (IAM user or role), what action was performed (CreateUser, RunInstances, etc.), when it happened (ISO-8601 timestamp), from which IP, and what parameters were passed. This is the raw data source for DocuGen AI.

**Trail configuration**:
- Trail name: `docugen-trail`
- Region: `us-east-1`
- Log delivery: S3 bucket `docugen-cloudtrail-logs-523761210523`
- Delivery path: `AWSLogs/{account_id}/CloudTrail/{region}/YYYY/MM/DD/`

CloudTrail delivers logs approximately every 5–15 minutes. Logs are compressed (`.json.gz`) and contain multiple events per file.

### S3 Buckets

**docugen-cloudtrail-logs-523761210523** (read-only from app perspective):
- CloudTrail writes here automatically
- Application reads these files via the S3 client service
- Organized by account → service → region → date

**docugen-reports-523761210523** (write-only from app perspective):
- Application writes generated reports here
- Organized by date: `reports/YYYY-MM-DD/`
- Stores both Markdown reports and JSON metadata

### IAM

- IAM user: `docugen-dev`
- Required permissions: CloudTrail read (S3 bucket read), S3 write (reports bucket), Bedrock model invocation (Claude 3.5 Sonnet + Titan V2)
- Authentication: Standard AWS credential chain — environment variables, then `~/.aws/credentials`
- No hardcoded credentials anywhere in the codebase

### Amazon Bedrock Model Access

Two models must be explicitly enabled in the Bedrock console before use:
1. **Claude 3.5 Sonnet** (`us.anthropic.claude-3-5-sonnet-20241022-v2:0`) — LLM
2. **Amazon Titan Embeddings V2** (`amazon.titan-embed-text-v2:0`) — Embeddings

---

## 16. Performance Characteristics

### Latency per Query

**Typical total**: 30–60 seconds

| Step | Typical Duration | Bottleneck |
|---|---|---|
| Time Parsing | 5–10 seconds | Bedrock API call |
| Log Analysis | 5–15 seconds | S3 download + gzip decompression |
| Event Filter | 2–3 seconds | Bedrock API call |
| Retrieval | 2–3 seconds | Titan embed + Pinecone query |
| Report Synthesis | 10–20 seconds | Bedrock API call (largest response) |
| Store Report | 1–2 seconds | Two S3 uploads |

The dominant bottleneck is Bedrock API calls. There are 4 Claude calls per pipeline run; each takes 5–10 seconds. The report synthesis call is the longest because the response (a full multi-section report) is the largest output (~4000 tokens).

### First-Run Indexing

~1–2 minutes on first startup only. 12 documents → ~200 chunks → ~200 Titan embedding API calls (~0.5–1 second each). Subsequent startups: ~1 second (index_has_data() check).

### Optimization Opportunities

| Optimization | Impact | Effort |
|---|---|---|
| Streaming report generation | User sees output progressively, eliminates 30-second wait | Medium |
| Parallel event filter + retrieval | Both are independent; could run simultaneously | Low |
| Cache time parsing for common phrases | "yesterday" always maps to same result given same date | Low |
| Cache embedding for identical queries | Repeated identical queries skip Titan call | Low |

---

## 17. Security Considerations

### Secrets Management

**Implemented**:
- AWS credentials via environment variables or `~/.aws/credentials` — never hardcoded
- Pinecone API key via `.env` file, loaded with `python-dotenv`
- `.env` is gitignored — secrets never enter version control
- `.env.example` provides the template for required variables without actual values

**Production recommendations**:
- Use AWS Secrets Manager for the Pinecone API key (rotation, audit log)
- Use an IAM role (EC2 instance profile, ECS task role) instead of an IAM user — roles have no long-lived credentials
- Enable S3 bucket versioning on the reports bucket to prevent accidental overwrites

### Data in Transit and at Rest

- All AWS API calls use HTTPS (TLS 1.2+) — encrypted in transit
- S3 objects are encrypted at rest by default (SSE-S3)
- Bedrock API calls: data processed in AWS infrastructure, not sent to third parties
- No customer data ever leaves AWS infrastructure (all services: Bedrock, S3, CloudTrail are AWS-native)

### Report Access Control

Currently, reports are stored in a private S3 bucket accessible only to the IAM user. For production:
- Enable S3 bucket policy to restrict access to specific principals
- Consider S3 Object Lock for immutable audit trails (compliance requirement)
- Add CloudTrail logging for the reports bucket itself (logs on logs)

---

## 18. Limitations & Honest Assessment

### Scope Limitations

**Single account, single region**: The system reads CloudTrail logs from one AWS account and one region (`us-east-1`). An enterprise with dozens of accounts and multi-region deployments would need the pipeline to accept account lists and region lists, building S3 prefixes dynamically.

**Single-query interface**: One question at a time. No batch processing. A security team reviewing a week of activity would need to submit seven separate queries.

**No real-time analysis**: CloudTrail delivers logs with a 5–15 minute delay. The system analyzes historical logs, not live events. For real-time incident response, this is a limitation.

### Technical Limitations

**Latency**: 30–60 seconds per query. This is acceptable for a report generation use case (users expect to wait for a document) but would be unacceptable for interactive chat. The primary bottleneck is the series of Bedrock API calls.

**No streaming**: The Streamlit UI shows a spinner for the full 30–60 seconds, then displays the complete report at once. Streaming the report synthesis would dramatically improve perceived performance — the user would see text appearing within 10 seconds.

**Error handling is basic**: The pipeline has no retry logic for transient failures (Bedrock timeout, S3 rate limiting, Pinecone unavailability). A network error fails the entire pipeline with a generic error message.

**Documentation coverage**: The 12 documentation files cover the most common AWS security topics (IAM, EC2, S3, CloudTrail, Lambda). Queries about less-common services (EKS, RDS, DynamoDB, API Gateway) may receive lower confidence scores and include the disclaimer.

### RAG Limitations

**CONFIDENCE_THRESHOLD calibration**: The 0.50 threshold was calibrated on the specific 12 documentation files and Titan V2. Adding new documentation files or switching embedding models would require recalibration.

**Cosine similarity as a proxy for quality**: A high cosine similarity means the retrieved chunk is semantically related to the query — it does not guarantee the chunk is informative or specifically applicable to the events found. A chunk about IAM general concepts will always score highly for IAM queries, even if the specific events are about a rarely-discussed IAM feature not well-covered in the documentation.

**Static documentation**: The documentation files are manually curated and manually updated. AWS regularly updates its services and best practices. Outdated documentation produces outdated recommendations.

---

## 19. Future Enhancements

### Streaming Output

Replace the 30–60 second wait with progressive rendering. Bedrock's Converse API supports streaming responses (`converse_stream`). As Claude generates the report, each token would be pushed to Streamlit via `st.write_stream()`, making the report appear word-by-word. The user experiences immediate feedback instead of a blank screen.

### Multi-Account and Multi-Region Support

Accept an account list and region list as parameters. The log analysis agent would iterate through all account/region combinations, merge events, and produce a unified cross-account report. This requires: (1) a Pinecone namespace per account for separate report storage, (2) parameterized S3 prefix construction, (3) merged event deduplication.

### Automated Alerting

Instead of requiring a user to submit a query, run the pipeline on a schedule (EventBridge + Lambda trigger). Detect predefined high-risk patterns: multiple failed console logins, privilege escalation (user created + admin policy attached), IAM changes outside business hours. Automatically generate a report and deliver it via SNS or email. This transforms DocuGen from reactive to proactive.

### Expanded Documentation Coverage

Index documentation for all major AWS services: RDS, EKS, DynamoDB, API Gateway, VPC, Lambda, etc. The indexer and retrieval code require no changes — adding `.md` files to `docs/aws/` and re-running the indexer (after deleting the Pinecone index to force re-indexing) is sufficient.

### Report Dashboard

A second Streamlit page listing all previously generated reports stored in S3 (reading the metadata JSON files). A security team could filter by date, query type, risk level, or confidence score. Reports could be searched by keyword. This makes the S3 report archive accessible without manual S3 bucket browsing.

### Confidence-Weighted Recommendations

Currently, recommendations are either confident or disclaimed. A more nuanced approach would weight individual recommendations by the similarity score of the specific documentation chunk that generated them. High-similarity-backed recommendations get priority; lower-similarity recommendations are flagged individually with their source score.

### CWE/CVE Integration

Enrich the report with CVE or CWE references when CloudTrail events match known vulnerability patterns. For example, a security group rule opening port 22 to 0.0.0.0/0 could reference the OWASP Cloud Security Top 10 entry for excessive permissions. This would require adding a secondary knowledge base of security vulnerabilities alongside the AWS documentation.

### Human Feedback Loop

Add a thumbs up/down feedback button in the Streamlit UI. Store feedback alongside the report metadata in S3. Over time, analyze which queries produce low-rated reports (likely to correlate with low confidence scores or poor documentation coverage). Use this signal to prioritize documentation expansion and prompt improvement.

### CI/CD and Automated Testing

Add a GitHub Actions workflow that runs the full test suite on every push. Include a documentation coverage check that warns when a new CloudTrail event type is added to the categorization dictionary but no corresponding documentation file exists in `docs/aws/`. This keeps the documentation aligned with the categorization schema.

---

*This report covers the complete technical and business design of DocuGen AI — from first-principles motivation through every architectural decision, agent implementation, service integration, and future direction.*
