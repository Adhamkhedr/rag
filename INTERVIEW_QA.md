# DocuGen AI — Interview Questions & Answers

---

## Table of Contents

1. [Tell Me About This Project](#1-tell-me-about-this-project)
2. [Business Problem & Motivation](#2-business-problem--motivation)
3. [Architecture & Design Decisions](#3-architecture--design-decisions)
4. [The Six Agents — Deep Dive](#4-the-six-agents--deep-dive)
5. [RAG System](#5-rag-system)
6. [AWS CloudTrail & S3](#6-aws-cloudtrail--s3)
7. [LangGraph Pipeline](#7-langgraph-pipeline)
8. [Services & Infrastructure](#8-services--infrastructure)
9. [Testing](#9-testing)
10. [Limitations & What I Would Improve](#10-limitations--what-i-would-improve)
11. [Code-Specific Questions](#11-code-specific-questions)

---

## 1. Tell Me About This Project

**Q: Tell me about this project.**

A: DocuGen AI is a multi-agent system that automatically generates audit-ready security incident reports from AWS CloudTrail logs. The idea is simple — a security analyst types a plain English question like "What IAM changes happened yesterday?" and within 30 to 60 seconds receives a fully structured security report with a timeline of events, risk assessment, and recommended actions.

The core technical challenge was making these reports trustworthy and verifiable, not just readable. Anyone can ask an LLM to write a security report — but if the recommendations come purely from the model's training data, there's no way to verify them. So I built a RAG system on top of it. Before Claude writes a single sentence, the system searches a curated set of AWS documentation files stored in a Pinecone vector database and retrieves the most relevant chunks. The report then cites those specific documentation sources by filename — so an auditor can open "iam-best-practices.md" and verify that the recommendation is real and current.

The pipeline is orchestrated by LangGraph and runs six specialized agents in sequence: time parsing, log analysis, event filtering, retrieval with a confidence-gated retry loop, report synthesis, and report storage to S3. Each agent has a single responsibility, which makes the system easy to test, debug, and explain.

The system is fully AWS-native — CloudTrail for logs, S3 for storage, Amazon Bedrock for both the LLM (Claude 3.5 Sonnet) and embeddings (Titan Embeddings V2), and Pinecone as the vector database. The UI is built with Streamlit.

What I'm most proud of is the confidence-gated retry loop. After every documentation retrieval attempt, the system calculates an average cosine similarity score across the top 5 results. If the score is below the threshold, it automatically broadens the search query and tries again — up to three times — before proceeding with a disclaimer. The system never silently produces an unreliable report. It's always transparent about its own confidence.

---

**Q: What is the key innovation in this project?**

A: The key innovation is documentation-grounded reporting. There are two types of output an AI system can produce: a log dump — "user X created an IAM role" — and an actual security finding — "user X created an IAM role granting full S3 access; per AWS IAM best practices, roles should follow least-privilege principles and be scoped to specific actions." The RAG component is what transforms the former into the latter. Without it, Claude writes from memory. With it, Claude writes from your actual documentation — making the output verifiable and audit-ready.

The second innovation is the confidence-gated retry loop — the system measures the quality of its own retrieval and self-corrects before writing the report.

---

## 2. Business Problem & Motivation

**Q: What problem does this solve?**

A: AWS CloudTrail records every API call in your account. On a typical active account, this generates hundreds to thousands of events per day stored as compressed JSON files in S3 — each event with 50+ fields. When a security team needs to answer a question like "were there any unauthorized IAM changes last night?", the raw answer is buried in those files.

Traditionally answering this requires: finding the right S3 folder, downloading files, decompressing them, writing SQL queries in Athena to filter events, interpreting raw JSON fields, manually looking up AWS documentation to understand the risk, and writing a report by hand. This process takes hours, needs technical expertise, and only happens reactively — after something already went wrong.

DocuGen AI removes every manual step. You type one sentence and get a professional report in 60 seconds.

---

**Q: Why does grounding the report in documentation matter?**

A: Because "user X created an IAM role" is just a log dump — it tells you what happened but not why it matters or what to do about it. A grounded report says "user X created an IAM role granting full S3 access — per AWS IAM best practices (iam-best-practices.md), roles should follow least-privilege principles and be scoped to specific actions." That's an actionable security finding backed by a verifiable source.

Without RAG, Claude writes from its training data which could be outdated or hallucinated. With RAG, Claude writes from your actual documentation. An auditor can open the referenced file and confirm the recommendation is real. That's the difference between a log viewer and a security analyst.

---

**Q: Who are the target users?**

A: Security analysts investigating suspicious activity, cloud engineers doing routine infrastructure audits, compliance officers generating evidence for audit cycles, DevOps teams understanding what happened during an incident, and CISOs reviewing executive-level security summaries. Essentially anyone who needs to make sense of AWS activity without being a CloudTrail expert.

---

**Q: Why is this useful for compliance?**

A: Compliance frameworks like SOC 2, ISO 27001, and PCI-DSS require companies to prove they are actively monitoring their systems. An auditor asks "show me evidence that you monitored your AWS account last month." DocuGen automatically creates that evidence — a timestamped structured report stored in S3 with traceable metadata: when it was generated, which model was used, what confidence score was achieved, which documentation sources were referenced. This is directly usable as audit evidence. A chatbot conversation is not.

---

## 3. Architecture & Design Decisions

**Q: Why a multi-agent architecture instead of one big prompt?**

A: Separation of concerns. Each agent has a single responsibility — time parsing, log fetching, event filtering, retrieval, report writing, storage. This makes the system easier to test (each agent can be tested in isolation), easier to debug (when something fails, you know exactly which step failed), and easier to explain. It also means only the report synthesis agent performs deep LLM reasoning — the most expensive and hallucination-prone step. All the data gathering happens before Claude writes anything.

---

**Q: Why LangGraph specifically?**

A: The key feature I needed was conditional edges — after retrieval, the pipeline must evaluate confidence and either proceed or loop back and retry. With plain function calls, you'd need manual if/else logic and manual state passing. LangGraph expresses this as a declarative graph with a conditional edge — clean, visualizable, and maintainable. It also manages shared state automatically: each agent returns a dict of updates and LangGraph merges them into the shared state. LangGraph is also the industry-standard tool for this pattern, which adds portfolio value.

---

**Q: Why Amazon Bedrock instead of the Anthropic API directly?**

A: Keeps the entire stack AWS-native. The same AWS credentials used for S3 and CloudTrail are used for Bedrock — single IAM policy governs everything. No separate API key to manage for the LLM. It also means the solution can run entirely inside a VPC without outbound internet traffic, which matters for enterprise deployments. Both Claude 3.5 Sonnet and Titan Embeddings V2 are available through the same Bedrock service.

---

**Q: Why two different Bedrock APIs — converse() for Claude and invoke_model() for Titan?**

A: The `converse()` API is a standardized chat interface — same message format regardless of which chat model you use. It works for models that generate text responses. Titan Embeddings is not a chat model — it takes text in and returns a vector of 1024 floating-point numbers. It has no concept of conversation turns. `invoke_model()` is the lower-level general-purpose API that sends raw JSON and receives raw JSON, which is what embedding models require. Using the wrong API for either would fail.

---

**Q: Why Pinecone over FAISS or other options?**

A: FAISS is excellent but local — it stores vectors in memory on a single machine. Pinecone is a managed cloud vector database. For this project, Pinecone demonstrates real vector database usage (not a local approximation), is accessible from any machine without setup, requires zero infrastructure maintenance, and the free tier easily handles the ~200 vectors we generate. It also adds portfolio value — showing familiarity with cloud-native vector database patterns.

---

**Q: Why Streamlit for the UI?**

A: The primary deliverable is the report, not the interface. The user workflow is: ask question → wait → read report → download it. Streamlit covers this entirely in about 50 lines of Python with no HTML, CSS, or JavaScript. Built-in Markdown rendering is perfect for reports. Download buttons, spinners, and collapsible JSON panels are all native components. For a project where the backend is the focus, Streamlit was the right call.

---

## 4. The Six Agents — Deep Dive

**Q: Walk me through Agent 1 — Time Parsing.**

A: Its one job is converting the user's plain English time expression into exact ISO-8601 timestamps. CloudTrail logs are stored in S3 organized by date — `AWSLogs/.../2026/02/07/` — so before making any S3 calls, the system needs to know the exact dates involved. The agent injects the current UTC time into Claude's prompt and asks it to interpret the expression. "Yesterday" becomes `{"start": "2026-02-07T00:00:00Z", "end": "2026-02-07T23:59:59Z"}`. Temperature is 0.0 for determinism, max tokens is 200 since the output is always a small JSON object.

The reason we use Claude for this rather than hardcoded logic is that expressions like "last Tuesday afternoon" or "the past 3 hours" are too varied for if/else logic. Claude handles all of them naturally. The current UTC time is injected because Claude has no access to a clock — without a reference point it cannot interpret relative expressions.

---

**Q: Walk me through Agent 2 — Log Analysis.**

A: This is the most computationally intensive agent. It runs seven phases.

Phase 1 builds the S3 folder paths for each date in the time range. Phase 2 lists all `.json.gz` files in those folders and uses regex to extract timestamps from filenames — skipping files clearly outside the range without downloading them. This matters because a busy account can have hundreds of files per day and we don't want to download all of them.

Phase 3 downloads and decompresses the relevant files. CloudTrail logs are gzip-compressed. Phase 4 does exact timestamp filtering at the event level — because a file named T1200Z might contain events from 11:50 AM and 12:10 PM mixed together. The filename timestamp is just when CloudTrail created the file, not when the events occurred. So we check each individual event's `eventTime` field and discard anything outside the exact range.

Phase 5 reduces each event from 50+ fields down to 7: who, what, when, from where, which region, what type, and what was acted upon. Categorization is done by dictionary lookup — `CreateUser` is always IAM_CHANGE, no AI needed. Phase 6 separates noise events — routine AWS background calls like GetBucketAcl and ListBuckets — moving them to the end of the list so they don't dominate the analysis. Phase 7 sends up to 50 security-relevant events to Claude for a 2–3 sentence summary that travels through the rest of the pipeline.

---

**Q: Why reduce events from 50+ fields to 7?**

A: Two reasons. First, token cost — when sending events to Claude later, every field costs tokens. Sending 50 events with 50+ fields each is thousands of tokens of noise. Second, LLM focus — the more irrelevant content in a prompt, the more likely the model misses what matters. The 7 fields are exactly what a security analyst needs: who did it, what they did, when, from where, in which region, what type of action, and what was acted upon. Everything else — TLS version, request ID, event version — adds zero value to a security report.

---

**Q: Walk me through Agent 3 — Event Filter.**

A: After Agent 2, we have events from multiple categories. But if the user asked "What IAM changes happened yesterday?", the AUTH_EVENT and SECURITY_GROUP events are irrelevant. Sending them downstream would confuse the RAG retrieval — it would search for documentation matching IAM AND security groups AND S3 all at once — and would cause the report to lose focus.

Claude is given the user's original question and the list of categories found in the events. It returns only the relevant category names. The code then filters the event list accordingly. For broad questions like "what happened today?", Claude correctly returns all categories.

We chose this LLM-based filtering over two alternatives: sending everything (unfocused RAG, wastes tokens) or query-biased ranking (reorders results but doesn't remove irrelevant events — the noise is still in the prompt). Filtering at the source is cleanest.

Importantly, the original question never gets discarded — it stays in shared state the entire time and is included in Agent 5's prompt. The filtering removes noise around the question, not the question itself.

---

**Q: Walk me through Agent 4 — Retrieval.**

A: Its job is to search the AWS documentation in Pinecone and find the chunks most relevant to the events found.

First, the agent builds a purpose-built retrieval query from the relevant category — not the raw user question. The user might ask "What IAM changes happened yesterday?" which is about time, not about IAM concepts. A purpose-built query like "IAM users roles policies best practices least privilege credentials" is optimized to match documentation content.

The query gets embedded by Titan Embeddings into a 1024-dimensional vector, sent to Pinecone, and the top 5 most similar documentation chunks are returned with their cosine similarity scores. The confidence score is the average of those 5 scores.

If confidence is below 0.50, the system retries with a broader pre-written query. Each category has its own specific first query, but attempts 2 and 3 are the same across all categories — they cast a wider net. After 3 attempts, if confidence is still low, the pipeline proceeds anyway but tells Claude to include a disclaimer. The system never blocks — it always produces a report but is transparent about its reliability.

One honest limitation: the retrieval queries are hardcoded strings, not generated from the actual events. A better approach would be to send the specific events to Claude and ask it to write a search query tailored to what actually happened — which would produce more targeted documentation matches and likely reduce retries.

---

**Q: Walk me through Agent 5 — Report Synthesis.**

A: This is where everything comes together. Claude receives: the original question, the time range, the filtered events balanced at up to 5 per category, the event summary, the first 500 characters of each retrieved documentation chunk, and the confidence score.

The report structure is enforced via the system prompt — Claude is told exactly which sections to write. This ensures every report has the same format regardless of the query, which matters for compliance and auditability.

The confidence score directly changes Claude's instructions. Above 0.50: write a confident authoritative report citing documentation. Below 0.50: include a prominent warning that documentation grounding was limited. The system never pretends to be more reliable than it is.

---

**Q: Walk me through Agent 6 — Store Report.**

A: It saves two files to S3 per report. A Markdown file — the human-readable report. And a JSON metadata file — containing the report ID, original query, time range, generation timestamp, model used, confidence score, sources referenced, and event count. The Markdown is for analysts to read; the metadata is for audit systems to query programmatically.

Strictly speaking, this doesn't need to be a separate agent — it's just two S3 function calls with no reasoning involved. It could have been done at the end of Agent 5. The reason it's separate is clean separation of concerns: generation and storage are different responsibilities, they can be tested independently, and changing where reports are stored only requires touching Agent 6.

---

## 5. RAG System

**Q: What is RAG and why do you use it?**

A: RAG stands for Retrieval-Augmented Generation. Instead of relying only on the LLM's training data — which may be outdated and can't be verified — you retrieve specific real documents at query time and include them in the prompt. This grounds the LLM's output in verifiable sources. A report can say "per iam-best-practices.md, roles should follow least-privilege principles" and an auditor can open that file and confirm it. You can't audit "per Claude's training data."

AWS security best practices evolve. IAM policies change. New event types are added. By indexing curated up-to-date documentation and retrieving it at query time, reports stay current and every recommendation is traceable.

---

**Q: Walk me through the indexing process.**

A: On first startup only. The indexer reads each of the 12 AWS documentation Markdown files, splits each into chunks of ~1000 characters with 200-character overlap using LangChain's RecursiveCharacterTextSplitter, embeds each chunk using Titan Embeddings V2 into a 1024-dimensional vector, and uploads all vectors to Pinecone with metadata containing the original text and source filename. About 200 chunks total. Takes 1–2 minutes.

On every subsequent startup, the indexer checks if Pinecone already has vectors. If yes, it skips entirely. The check takes about 1 second.

---

**Q: Why chunk documents instead of embedding the whole document?**

A: A full document about IAM covers users, roles, policies, and best practices — its embedding represents the average meaning of all those topics, too vague for precise retrieval. A 1000-character chunk covers one focused topic and produces a vector representing that specific concept. When you search for "IAM least privilege", a chunk specifically about least privilege will match far better than the average of the whole document.

---

**Q: What is the 200-character overlap for?**

A: Sentences often span chunk boundaries. Without overlap, a key sentence starting at character 950 and ending at character 1050 would get cut in half — partially lost in both chunks. The 200-character overlap ensures sentences at boundaries appear fully in at least one chunk. Chunk 0 covers characters 0–999, chunk 1 covers 800–1799, chunk 2 covers 1600–2599, and so on.

---

**Q: What is cosine similarity?**

A: It measures the angle between two vectors — how similar their directions are — on a scale of 0 to 1. A score of 1.0 means identical meaning, 0.0 means completely unrelated. It measures semantic direction, not text length. A short query "IAM least privilege" will match a long documentation paragraph because they point in the same semantic direction, even though their vectors have very different magnitudes. That's why we normalize vectors — to ensure cosine similarity measures direction only, not size.

---

**Q: Why is the confidence threshold 0.50 and not higher?**

A: Titan Embeddings V2 operates on a different scale than models like OpenAI's text-embedding-ada-002. Empirically, a score of 0.65 with Titan V2 represents a very good semantic match — equivalent to what might score 0.88 with ada-002. Setting the threshold at 0.75 would cause false failures — the system would retry even when it found genuinely relevant documentation. The 0.50 threshold was calibrated by running actual queries and observing what score consistently separated relevant from irrelevant results.

---

**Q: Why not use the raw user question as the retrieval query?**

A: The user question is written for human communication — "What IAM changes happened yesterday?" is about time and event type, not about IAM concepts. Embedding that sentence and searching Pinecone with it might return documentation about CloudTrail timestamps or date formats — not IAM best practices. A purpose-built query like "IAM users roles policies best practices least privilege credentials" is optimized to match documentation content and produces much better results.

---

## 6. AWS CloudTrail & S3

**Q: What is AWS CloudTrail?**

A: CloudTrail is AWS's audit logging service — a security camera for your AWS account. It automatically records every API call made: who performed the action (IAM user or role), what action (CreateUser, RunInstances, etc.), when (ISO-8601 timestamp), from which IP, and what parameters were used. Every time someone creates a user, launches a server, changes a security group, or logs into the console — CloudTrail writes it down.

Logs are delivered to an S3 bucket as gzip-compressed JSON files every 5–15 minutes, organized by date: `AWSLogs/{account_id}/CloudTrail/{region}/YYYY/MM/DD/`.

---

**Q: Why are there two levels of filtering when reading logs?**

A: Because the file organization is approximate, not exact.

Level 1 filters at the file level — we extract the rough timestamp from each filename and skip files clearly outside the time range. This avoids downloading hundreds of irrelevant files.

Level 2 filters at the event level — after downloading, we check each individual event's `eventTime` field. A file named T1200Z might contain events from 11:50 AM and 12:10 PM mixed together because CloudTrail batches events based on when the file is created, not when the events occurred. Without level 2 filtering, events outside the exact range would slip into the report.

Together: level 1 eliminates unnecessary downloads, level 2 ensures precision at the event level.

---

**Q: What is the S3 paginator and why do you use it?**

A: S3 list operations return a maximum of 1000 items per API call. A busy AWS account can generate more than 1000 log files in a single day. Without a paginator, the second batch of files would never be seen and those events would be silently missed. The paginator automatically handles continuation tokens — it keeps making requests until all files are listed, regardless of how many there are.

---

**Q: Why not use the CloudTrail LookupEvents API instead of reading from S3?**

A: LookupEvents is limited to 90 days of history and has strict rate limits. Reading from S3 gives access to the full log history, better performance for bulk reads, and is the standard production pattern for security tools that consume CloudTrail logs at scale.

---

## 7. LangGraph Pipeline

**Q: How does LangGraph manage state across agents?**

A: All agents share a single `DocuGenState` TypedDict. Each agent reads what it needs from the state, does its work, and returns a dict containing only the fields it updated. LangGraph automatically merges that dict back into the shared state. The next agent in the pipeline sees the updated state. Think of it like a shared notepad that gets passed along — each agent reads from it and writes to it.

---

**Q: Explain the confidence retry loop in detail.**

A: After every retrieval attempt, `confidence_check()` evaluates the average cosine similarity of the 5 retrieved documents. If it is ≥ 0.50, the conditional edge routes to `report_synthesis` — the loop exits and the report is written. If it is < 0.50 and fewer than 2 retries have been used, the edge routes to `increment_retry` which increments the retry counter, then loops back to `retrieval` with a broader query. If confidence is still low after 3 total attempts, the edge routes to `report_synthesis` anyway — but with a flag in state that tells Claude to include a disclaimer. The system always produces a report, never blocks.

---

**Q: Why TypedDict for the pipeline state?**

A: TypedDict provides static type checking — IDE autocompletion, mypy validation — without the overhead of a full dataclass. LangGraph requires a typed state class and TypedDict is the idiomatic choice. It documents exactly what fields exist at each stage, what their types are, and which are Optional (None until their agent runs). This makes every agent self-documenting about what it expects and what it produces.

---

**Q: What is a conditional edge in LangGraph?**

A: A conditional edge is a routing mechanism where the next node to execute is determined dynamically by a function, not hardcoded. After the retrieval node, instead of always going to report_synthesis, the `confidence_check` function runs and returns either "sufficient" or "retry". LangGraph uses that return value to decide whether to go to `report_synthesis` or `increment_retry`. Without conditional edges, you'd need manual if/else logic outside the graph.

---

## 8. Services & Infrastructure

**Q: What is the singleton pattern and why do you use it?**

A: Every service file creates its connection object once and reuses it. On the first call to `get_client()`, the connection is created and stored in a module-level variable. Every subsequent call returns the same object. Without this, every API call would create a new connection — including authentication handshakes and TCP setup — adding overhead across 6 agents making multiple calls each. The singleton creates it once for the lifetime of the Streamlit session.

---

**Q: Why temperature 0.0 for all Claude calls?**

A: Every Claude call in this pipeline has a deterministic, structured task — parse a time expression, list relevant categories, write a report following a strict structure. There is no benefit to randomness. Temperature 0.0 means the same input produces the same output, which is important for reproducibility and for the predictable JSON outputs that time parsing and event filtering require.

---

**Q: What does normalize=True do in your embedding calls?**

A: It scales every vector to unit length — magnitude of 1. Without normalization, a longer text produces a larger vector and appears "more similar" to everything just because of its size, not because of its meaning. Normalization removes that size bias so cosine similarity measures only semantic direction. This is required for meaningful similarity comparisons.

---

**Q: What is the difference between converse() and invoke_model() in Bedrock?**

A: `converse()` is a high-level standardized chat API — same message format across all Bedrock chat models. It's designed for models that generate text. `invoke_model()` is lower-level — it sends raw JSON and receives raw JSON. It's required for models that don't follow the chat paradigm, like Titan Embeddings, which returns a vector of numbers rather than a text response. Using converse() with an embeddings model would fail.

---

## 9. Testing

**Q: How do you test a system that depends on AWS and Pinecone?**

A: All external services are mocked using Python's `unittest.mock.patch`. We patch at the agent level — `agents.time_parsing.invoke_claude`, `agents.log_analysis.invoke_claude`, etc. This lets us test each agent's logic without making real API calls. Tests run in seconds, cost nothing, and pass regardless of AWS account state or network availability.

---

**Q: What does the integration test verify?**

A: It mocks all 4 Claude calls (time parsing, event summary, category filter, report generation), the Titan embedding calls, S3 file listing and reading, Pinecone querying, and S3 report storage. Then it runs `run_pipeline("What IAM changes happened yesterday?")` end-to-end and verifies: the final report exists and contains "Incident Report", the metadata has the correct event count, and the retrieval confidence is above zero.

---

**Q: What are the biggest gaps in your test coverage?**

A: Honestly, there are no tests for error scenarios — Bedrock API timeout, S3 file not found, invalid JSON from Claude, Pinecone unavailability. All tests cover the happy path only. The retry loop logic is tested but not end-to-end through the full pipeline. And some complex helper functions like `_extract_target()` in log analysis have no dedicated unit tests. In production these would be the first things to add.

---

## 10. Limitations & What I Would Improve

**Q: What are the main limitations of this system?**

A: A few honest ones.

**Latency** — 30 to 60 seconds per query. The bottleneck is 4 sequential Bedrock API calls. Acceptable for report generation but not for interactive use.

**Hardcoded retrieval queries** — The RAG search queries are pre-written strings per category, not generated from the actual events. A smarter approach would generate the search query dynamically from the specific events found, producing more targeted documentation matches.

**No error handling on API calls** — If Bedrock times out or S3 is temporarily unavailable, the pipeline crashes with a generic error. There's no retry logic for transient failures.

**Single account and region** — The system reads from one AWS account in one region. Enterprise deployments typically span dozens of accounts and multiple regions.

**Static documentation** — The 12 documentation files are manually curated and manually updated. Outdated docs produce outdated recommendations.

---

**Q: What would you change or improve if you built this again?**

A: The biggest improvements would be:

First, streaming output. Instead of showing a spinner for 60 seconds and then the full report at once, stream the report synthesis token by token using Bedrock's `converse_stream` API. The user sees output within 10 seconds.

Second, dynamic retrieval query generation. Instead of hardcoded category strings, send the actual events to Claude and ask it to write a search query tailored to what specifically happened. Better queries mean better documentation matches and fewer retries — potentially saving API calls overall.

Third, proper error handling on every external API call — retry logic with exponential backoff for transient failures, circuit breakers, and graceful degradation (e.g., if Pinecone is down, generate a report without RAG grounding but with a clear disclaimer).

Fourth, multi-account and multi-region support — parameterize the account ID and region so the pipeline can analyze activity across an entire organization.

---

**Q: What happens if confidence never reaches the threshold after 3 attempts?**

A: The pipeline proceeds to report synthesis anyway. The confidence score is passed into the prompt and Claude is explicitly told to include a prominent warning at the top of the report: documentation grounding was limited and recommendations may not be fully based on current AWS guidance. The system never blocks — it always produces a report, but never lies about its own reliability.

---

## 11. Code-Specific Questions

**Q: What does the `global` keyword do in your get_client() functions?**

A: Without `global`, writing `_client = boto3.client(...)` inside a function creates a local variable that disappears when the function ends. `global _client` tells Python "I'm referring to the `_client` defined at the top of the module, not creating a new local one." This is how the singleton pattern persists the connection across multiple calls.

---

**Q: What is RecursiveCharacterTextSplitter?**

A: A text splitter from LangChain that breaks documents into chunks of a specified size. "Recursive" means it tries to split at natural boundaries first — paragraph breaks, then line breaks, then spaces, then individual characters — so it avoids cutting sentences in half when possible. We use it with chunk_size=1000 and chunk_overlap=200.

---

**Q: What is boto3?**

A: The official AWS SDK for Python. It lets Python code call any AWS service — S3, Bedrock, IAM, EC2, CloudTrail, etc. In this project, we use it to create clients for S3 (reading logs, storing reports) and Bedrock Runtime (calling Claude and Titan models).

---

**Q: What does graph.compile() do?**

A: It takes all the nodes and edges defined — via `add_node`, `add_edge`, `add_conditional_edges` — and turns them into a runnable application object. Before compile, you have a graph definition. After compile, you have an object you can call `.invoke()` on to actually execute the pipeline.

---

**Q: Why use Optional in the state TypedDict?**

A: `Optional` means the field can be None. At the start of the pipeline, only `query` has a value — everything else is None because no agent has run yet. As agents run, they populate their fields. Without Optional, Python's type checker would flag None values in the initial state as errors. It also signals to readers which fields are filled at which point in the pipeline.

---

**Q: What does json.dumps() vs json.loads() do?**

A: `json.dumps()` converts a Python dict or list into a JSON string — used when sending data to APIs that expect JSON. `json.loads()` converts a JSON string back into a Python dict or list — used when receiving data from APIs that return JSON strings. We use dumps when sending events to Bedrock and loads when parsing CloudTrail log files and Claude's structured JSON responses.

---

**Q: Why does the time parsing agent strip markdown code fences?**

A: Claude occasionally wraps JSON responses in markdown formatting like ` ```json ... ``` `. If you try to parse that directly with `json.loads()`, it fails because the backticks are not valid JSON. The agent detects and strips these fences before parsing, making it robust to minor formatting variations in Claude's output.

---

*Prepared for interviews — covers high-level business context, architecture decisions, every agent in detail, RAG, AWS infrastructure, testing, and honest limitations.*
