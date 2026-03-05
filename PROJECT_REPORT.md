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

SOC 2, ISO 27001, and PCI-DSS are official security standards that companies must comply with — especially if they handle sensitive data or work with enterprise clients. Think of them as certifications that prove "this company takes security seriously." To get and maintain these certifications, companies must **prove** they are actively monitoring their systems. An auditor comes in and asks: *"Show me evidence that you monitored your AWS account last month."*

Not just "yes we monitored it" — they need an actual document with a timestamp, what was analyzed, what was found, and what actions were recommended.

Every report DocuGen generates is automatically saved to S3 with two files:

**The report itself** — a structured Markdown document with a timeline of events, findings, risk assessment, and recommendations.

**A metadata file** — a JSON file stored alongside it containing:
```json
{
  "generated_at": "2026-02-08T15:30:00Z",
  "query": "What IAM changes happened yesterday?",
  "model_used": "Claude 3.5 Sonnet",
  "retrieval_confidence": 0.72,
  "sources_referenced": ["iam-best-practices.md", "iam-users-guide.md"],
  "event_count": 42
}
```

An auditor can open this and verify: when the report was generated, what data was analyzed, which documentation backed the recommendations, and how confident the AI was. Everything is traceable.

**This is not a chatbot — it is a documentation system.** A chatbot gives you an answer in a conversation that disappears. DocuGen produces permanent, stored, structured documents — the same way a human analyst would write and file a security report. That is what makes it usable in a professional compliance context. Simply put: companies are legally required to prove they monitor their systems. DocuGen automatically creates that proof.

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

---

**One job**: Convert the user's plain English time expression into exact timestamps.

---

**Why is this needed?**

CloudTrail logs are stored in S3 organized by date in the folder path itself:
```
AWSLogs/
  523761210523/
    CloudTrail/
      us-east-1/
        2026/
          02/
            07/   ← all Feb 7 logs live here
            08/   ← all Feb 8 logs live here
```

To know which folder to look in, the system needs exact dates and times. But users type things like "yesterday", "last night", "this morning", or "last Tuesday." A computer cannot work with those expressions — it needs `2026-02-07T00:00:00Z` to `2026-02-07T23:59:59Z`.

---

**How it works**

1. The code checks the actual current UTC time using Python's `datetime.now()` — for example `2026-02-08T12:00:00Z`
2. It sends that current time to Claude along with the user's question:
   > *"Today is 2026-02-08T12:00:00Z. The user asked: 'What IAM changes happened yesterday?' — what is the time range they mean?"*
3. Claude interprets the expression and returns a JSON object:
```json
{"start": "2026-02-07T00:00:00Z", "end": "2026-02-07T23:59:59Z"}
```
4. That gets written to shared state and Agent 2 picks it up

**Why inject the current time into the prompt?**
Claude by itself has no access to a clock. Without being told what today's date is, it cannot interpret relative expressions like "yesterday" or "last Tuesday." Injecting the current UTC time gives Claude a reference point so it can calculate the correct dates every time.

**Why JSON output?**
The output needs to be machine-readable so the next agent can use it directly in code. Claude is explicitly instructed in the prompt to return only a JSON object — no explanation, no extra text. Temperature is set to 0.0 (fully deterministic) since this is a precise calculation, not a creative task. Max tokens is set to 200 since the response is always a small JSON object.

**Why Claude and not just code?**
You could hardcode "yesterday = today minus 1 day" — but what about "last Tuesday afternoon"? Or "the past 3 hours"? Or "this morning"? These expressions are too varied to handle with simple if/else logic. Claude handles all of them naturally.

**Handling LLM quirks**: Claude occasionally wraps JSON responses in markdown code fences (` ```json ... ``` `). The agent detects and strips these before parsing, making it robust to minor formatting variations.

**Output written to shared state**: `{"start": "2026-02-07T00:00:00Z", "end": "2026-02-07T23:59:59Z"}`

Agent 2 picks up from here.

---

### Agent 2: Log Analysis

**File**: `agents/log_analysis.py`
**Input**: `state["time_range"]`
**Output**: `state["log_findings"]` — `{events: [...], summary: "..."}`

---

**One job**: Get the CloudTrail logs for the time range Agent 1 found, and turn them into clean, useful events.

---

**Phase 1: Find the Right Folders**

Agent 1 gave us a time range, for example:
```
start: 2026-02-07T00:00:00Z
end:   2026-02-07T23:59:59Z
```

S3 stores CloudTrail logs in folders organized by date:
```
AWSLogs/
  523761210523/
    CloudTrail/
      us-east-1/
        2026/
          02/
            07/  ← this is where Feb 7 logs live
```

The code takes the dates from the time range and constructs the folder address for each date. If the range spans multiple days it does this for every day, building one folder path per day.

---

**Phase 2: List the Files, Filter by Filename**

Inside the Feb 7 folder there are many compressed files. Each filename contains a rough timestamp:
```
523761210523_CloudTrail_us-east-1_20260207T0100Z_abc.json.gz  ← created ~1 AM
523761210523_CloudTrail_us-east-1_20260207T0600Z_def.json.gz  ← created ~6 AM
523761210523_CloudTrail_us-east-1_20260207T1400Z_xyz.json.gz  ← created ~2 PM
```

The code uses regex to extract the timestamp from each filename (`T0100Z`, `T0600Z`, etc.) and skips files that are clearly outside the time range the user asked for. For example if the user asked for "this morning" (00:00 to 12:00), the file with `T1400Z` gets skipped entirely — never downloaded.

This matters because a busy AWS account can have hundreds of files per day. Skipping irrelevant ones saves time and bandwidth.

A paginator is used instead of a simple S3 list call because S3 list calls return a maximum of 1000 items at a time. A busy account can have more than 1000 files in a single day — the paginator automatically handles fetching the next batch until all files are listed.

---

**Phase 3: Download and Decompress**

For each file that passed the filename filter, the code:
1. Downloads the `.json.gz` file from S3
2. Decompresses it (CloudTrail saves all logs as gzip-compressed files to save storage space)
3. Parses the JSON inside

Each file now gives us a list of raw CloudTrail events — each one with 50+ fields.

---

**Phase 4: Exact Timestamp Filtering**

The filename timestamp is just when CloudTrail created the file — not the exact timestamps of the events inside it. A file named `T1200Z` might contain events from 11:50 AM and 12:10 PM mixed together because CloudTrail batches events and saves them every few minutes regardless of exact event times.

So the code opens every event, reads its individual `eventTime` field, and asks: is this event actually within the time range the user asked for?

- Event at 11:50 AM → keep it ✓
- Event at 12:10 PM → discard it ✗

**Two levels of filtering, each more precise than the last:**
```
Folders  →  filter by date             (eliminates wrong days)
  ↓
Files    →  filter by filename time    (eliminates obvious misses, saves bandwidth)
  ↓
Events   →  filter by exact timestamp  (eliminates edge cases at boundaries)
```

---

**Phase 5: Simplify and Categorize**

Each raw CloudTrail event has 50+ fields. Here is what one event actually looks like before simplification:

```json
{
    "eventVersion": "1.08",
    "userIdentity": {
        "type": "IAMUser",
        "principalId": "AIDAXT4UZ2SNQDEFXIL4",
        "arn": "arn:aws:iam::523761210523:user/docugen-dev",
        "accountId": "523761210523",
        "accessKeyId": "AKIAXT4UZ2SNQDEFXIL4",
        "userName": "docugen-dev"
    },
    "eventTime": "2026-02-07T14:23:00Z",
    "eventSource": "iam.amazonaws.com",
    "eventName": "CreateUser",
    "awsRegion": "us-east-1",
    "sourceIPAddress": "203.0.113.50",
    "requestParameters": {"userName": "test-user"},
    "responseElements": {"user": {...}},
    "requestID": "abc123-def456",
    "eventID": "xyz789",
    "tlsDetails": {"tlsVersion": "TLSv1.2", ...},
    ... 30+ more fields
}
```

After simplification:
```json
{
    "eventTime":      "2026-02-07T14:23:00Z",
    "eventName":      "CreateUser",
    "userName":       "docugen-dev",
    "sourceIP":       "203.0.113.50",
    "region":         "us-east-1",
    "category":       "IAM_CHANGE",
    "targetResource": "test-user"
}
```

**Why these 7 fields specifically?** They are exactly what Claude needs to write a security report:

| Field | Why Claude Needs It |
|---|---|
| `eventTime` | To build the timeline table |
| `eventName` | To describe what action was performed |
| `userName` | To identify who did it |
| `sourceIP` | An unusual IP is a red flag |
| `region` | Activity in unexpected regions is suspicious |
| `category` | To organize the report by type of activity |
| `targetResource` | To describe what was acted upon (e.g. name of new user) |

Everything else — `tlsDetails`, `requestID`, `principalId`, `eventVersion`, `eventSource` — is AWS internal metadata that adds zero value to a security report.

**Why reduce the fields at all?**
Two reasons. First, token cost — when we later send events to Claude, every field costs tokens. Sending 50 events with 50+ fields each is thousands of tokens of irrelevant noise. Second, LLM focus — the more noise in the prompt, the more likely Claude misses something important. Clean input produces better output.

**Categorization is done by dictionary lookup — not AI:**

| Category | Example Events |
|---|---|
| `IAM_CHANGE` | CreateUser, DeleteUser, AttachUserPolicy, CreateRole, CreateAccessKey |
| `AUTH_EVENT` | ConsoleLogin, GetSessionToken, AssumeRole |
| `SECURITY_GROUP` | AuthorizeSecurityGroupIngress, CreateSecurityGroup |
| `S3_CONFIG` | CreateBucket, PutBucketPolicy, PutBucketAcl |
| `EC2_LIFECYCLE` | RunInstances, TerminateInstances, StopInstances |
| `CLOUDTRAIL_CONFIG` | CreateTrail, StopLogging, DeleteTrail |
| `OTHER` | Anything not in the above lists |

**Why dictionary lookup and not Claude?**
The mapping is completely fixed and finite — `CreateUser` will always be an IAM change, no ambiguity. Using Claude here would add 2–3 seconds of latency per run and introduce a small chance of misclassification. Deterministic code is faster, cheaper, and 100% reliable for a well-defined mapping. The one weakness is that if AWS introduces a new event type tomorrow, it silently falls into "OTHER" — in production you would want an alert when "OTHER" events spike.

---

**Phase 6: Separate Noise**

On a typical AWS account, around 95% of CloudTrail events are routine background calls that AWS services make automatically — things like `GetBucketAcl`, `ListBuckets`, `HeadBucket`, `GenerateDataKey`. These are not security-relevant at all.

The code separates these noise events from the security-relevant ones. They are not deleted — just moved to the end of the list so they do not dominate the analysis. A typical day looks like:

- ~20–50 security-relevant events
- ~800+ noise events

The noise is preserved for full audit trail completeness but does not appear prominently in the report.

---

**Phase 7: Generate a Summary**

The code sends up to 50 of the security-relevant events to Claude and asks for a 2–3 sentence plain English summary. Something like:

> *"3 IAM users were created and 1 security group rule was modified. All actions were performed by docugen-dev from IP 203.0.113.50. No suspicious patterns detected."*

This summary travels with the events through the rest of the pipeline so subsequent agents have a quick overview without re-reading all events.

---

**Output written to shared state:**
- A clean list of simplified, categorized events
- The Claude-generated summary

Agent 3 picks up from here.

---

### Agent 3: Event Filter

**File**: `agents/log_analysis.py` (same file, separate function)
**Input**: `state["query"]`, `state["log_findings"]["events"]`
**Output**: `state["relevant_categories"]` — list of category names

---

**One job**: Look at all the events Agent 2 found and decide which categories are actually relevant to what the user asked.

---

**Why is this needed?**

After Agent 2 runs, we have events from multiple categories — for example:
- 38 IAM_CHANGE events
- 12 AUTH_EVENT events
- 5 SECURITY_GROUP events
- 3 S3_CONFIG events

But the user asked: *"What IAM changes happened yesterday?"*

The AUTH_EVENT, SECURITY_GROUP, and S3_CONFIG events have nothing to do with that question. If we send all of them to the next steps, two things go wrong:

1. **The RAG retrieval gets confused** — it searches for documentation matching IAM AND security groups AND S3 all at once, retrieving a scattered mix of unrelated docs instead of focused IAM documentation
2. **The report loses focus** — Claude tries to write about everything instead of directly answering the user's question

---

**How it works**

Claude is given two things:
1. The user's original question
2. The list of categories found in the events

It returns only the category names that are relevant:

> *"IAM_CHANGE"*

The code then filters the events list to only IAM_CHANGE events. The rest are set aside for the remainder of the pipeline.

**What about broad questions?**
If the user asks *"What happened today?"* or *"Give me a full security audit"*, Claude correctly returns all categories — nothing gets filtered out.

**What if Claude returns nothing?**
There is a fail-safe — if Claude's response is empty or unreadable, the code defaults to keeping all categories. The pipeline never gets blocked by a bad Claude response here.

---

**Why Claude for this and not code?**

You cannot hardcode this decision. *"What IAM changes happened?"* is obviously IAM only. But *"Were there any suspicious logins or permission changes?"* covers both AUTH_EVENT and IAM_CHANGE. Only Claude can read the question and make that judgment call correctly.

---

**Three approaches were considered:**

**Option A — Send everything, no filtering**
Skip Agent 3 entirely. Send all events from all categories directly to retrieval.
The problem: the retrieval query becomes vague, Pinecone returns a scattered mix of docs, and the report loses focus trying to cover everything.

**Option B — Claude decides (what we do)**
Ask Claude which categories are relevant. Filter events before anything else happens. Only relevant events move forward.
Most precise — the retrieval query is focused, the docs retrieved are targeted, the report answers the actual question.

**Option C — Query-biased ranking**
Don't filter anything out, but when searching Pinecone adjust the ranking so results closer to the user's question score higher.
The problem: it reorders results but doesn't remove irrelevant events. IAM, security group, and S3 events all still go into the prompt — just slightly reordered. The noise is still there.

Option B was chosen because it actually removes irrelevant events before they touch anything downstream, rather than just reordering or tolerating them. The cost is small — about 100 tokens and 2–3 seconds — which is worth the precision gain.

---

**The category is the bridge between the question and everything downstream**

Once Agent 3 identifies the relevant category, it drives everything that follows:

```
User question: "What IAM changes happened?"
        ↓
Agent 3: relevant category = IAM_CHANGE
        ↓
Agent 4: builds IAM-specific retrieval query → retrieves IAM documentation
        ↓
Agent 5: writes report using only IAM events + IAM documentation
```

Importantly, the original question is never discarded — it travels in the shared state the entire time and gets included in Agent 5's prompt directly. So Claude always sees three things when writing the report:

- The original question — what the user wants to know
- The filtered events — what actually happened that is relevant
- The retrieved documentation — why it matters and what to do about it

The filtering didn't replace the question. It removed the noise around it so Claude can answer it more precisely.

---

**Output written to shared state**: A list of relevant category names, e.g. `["IAM_CHANGE"]`

Agent 4 picks up from here.

---

### Agent 4: Retrieval with Confidence-Gated Retry

**File**: `agents/retrieval.py`
**Input**: Filtered events, relevant categories, retry count
**Output**: `state["retrieved_docs"]`, `state["retrieval_confidence"]`

---

**One job**: Search the AWS documentation stored in Pinecone and find the chunks most relevant to what happened in the logs.

---

**Why is this needed?**

At this point we have filtered events — for example 38 IAM_CHANGE events. Before Claude writes the report, we want to give it relevant AWS documentation to ground its recommendations. Without this, Claude writes from memory — which could be outdated or hallucinated. Agent 4 searches Pinecone and retrieves the actual documentation chunks most relevant to the events found.

---

**Why not just search using the user's question?**

The user asked: *"What IAM changes happened yesterday?"*

That question is written for a human — it's about time and event type. If you embed that sentence and search Pinecone with it, you might get documentation about CloudTrail time ranges or query syntax — not IAM best practices.

Instead the agent builds a purpose-built retrieval query using the category Agent 3 identified:

> *"IAM users roles policies best practices least privilege credentials"*

This is optimized to match IAM documentation content — exactly what Claude needs to write meaningful security recommendations.

---

**How the search works**

1. The retrieval query gets converted into a 1024-dimensional vector by Titan Embeddings
2. That vector gets sent to Pinecone
3. Pinecone finds the 5 most similar documentation chunks by cosine similarity
4. Returns them with their similarity scores

For example:
```
{source: "iam-best-practices.md",       similarity: 0.82}
{source: "iam-users-guide.md",          similarity: 0.79}
{source: "iam-policies-guide.md",       similarity: 0.71}
{source: "iam-roles-guide.md",          similarity: 0.68}
{source: "aws-security-fundamentals.md",similarity: 0.61}
```

---

**The Confidence Score**

After getting the 5 results, the agent calculates a confidence score:

```
confidence = (0.82 + 0.79 + 0.71 + 0.68 + 0.61) / 5 = 0.722
```

This answers: *how relevant is the documentation I just retrieved?*

- High score → found genuinely relevant docs → report will be well grounded
- Low score → found only vaguely related docs → report recommendations may be weak

**Why average all 5 and not just take the top 1?**
Because one excellent match surrounded by 4 poor matches is not good enough. Averaging forces all 5 results to be relevant — if the average is low, the retrieval genuinely failed and a retry makes sense.

---

**The Retry Loop — How Queries Broaden**

If confidence is below 0.50, instead of giving up the agent swaps to a pre-written broader query and tries again. The three queries per category are hardcoded in the code:

Each category has its own first query (specific to that category). Queries 2 and 3 are the same across all categories since by that point you are casting a wide net regardless:

```
Attempt 0 (category-specific, different per category):
  IAM_CHANGE:        "IAM users roles policies best practices least privilege credentials"
  AUTH_EVENT:        "AWS console login authentication MFA access keys session"
  SECURITY_GROUP:    "EC2 security groups inbound outbound rules network access"
  S3_CONFIG:         "S3 bucket policies access control public access encryption"
  EC2_LIFECYCLE:     "EC2 instances launch terminate security key pairs"
  CLOUDTRAIL_CONFIG: "CloudTrail logging monitoring trail configuration"

Attempt 1 (same for ALL categories):
  "AWS security best practices shared responsibility model monitoring access control"

Attempt 2 (same for ALL categories):
  "AWS cloud security IAM identity access management incident response compliance"
```

No AI is involved in this broadening — it is a simple lookup: attempt number → use this pre-written string. Fast, predictable, and free.

After 3 attempts, if confidence is still low, the pipeline proceeds anyway — but tells Claude to include a disclaimer in the report saying the documentation grounding was limited. **The system never blocks or crashes — it always produces a report, but is transparent about its confidence.**

---

**Honest limitation of this approach**

The hardcoded queries are static — they were written once and never change. They are based on the category label alone, not the actual events found. For example, if the events show a `CreateUser` action from a suspicious IP at 3 AM, the retrieval query is still the same generic `"IAM users roles policies best practices least privilege credentials"` — it ignores the specifics of what happened entirely.

A smarter approach would be to generate the retrieval query dynamically by sending the actual events to Claude and asking it to write a search query tailored to what specifically occurred. This is noted in the Future Enhancements section.

---

**Output written to shared state:**
- The 5 retrieved documentation chunks with their content and source filenames
- The confidence score

Agent 5 picks up from here.

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

### Dynamic Retrieval Query Generation

Currently Agent 4 uses hardcoded pre-written queries per category — the query is always the same regardless of what the actual events contain. A significantly better approach would be to send the actual filtered events to Claude and ask it to generate a search query tailored to what specifically happened:

> *"Based on these events — CreateUser at 3 AM from an unrecognized IP, followed immediately by AttachUserPolicy granting AdministratorAccess — write a search query to find the most relevant AWS security documentation."*

Claude would produce something like:
> *"AWS IAM privilege escalation AdministratorAccess unauthorized user creation least privilege suspicious activity"*

This query would retrieve far more targeted documentation than the generic hardcoded string. The cost is one extra Claude call (~3–5 seconds) which is worth it because better first-attempt queries mean fewer retries — potentially saving API calls overall.

### CI/CD and Automated Testing

Add a GitHub Actions workflow that runs the full test suite on every push. Include a documentation coverage check that warns when a new CloudTrail event type is added to the categorization dictionary but no corresponding documentation file exists in `docs/aws/`. This keeps the documentation aligned with the categorization schema.

---

*This report covers the complete technical and business design of DocuGen AI — from first-principles motivation through every architectural decision, agent implementation, service integration, and future direction.*
