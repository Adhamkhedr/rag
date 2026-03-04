# DocuGen AI — Interview Questions & Answers

---

## 1. HIGH-LEVEL / "Tell me about your project"

**Q: What is DocuGen AI?**
A: It's a multi-agent system that generates audit-ready incident reports from AWS CloudTrail logs. The user asks a natural-language question through a Streamlit web interface (e.g., "What IAM changes happened yesterday?"), and the system orchestrates multiple specialized agents through a LangGraph pipeline to analyze cloud activity logs, retrieve relevant AWS documentation via RAG, and produce a grounded, traceable security report.

**Q: What problem does it solve?**
A: In real AWS environments, security teams need to investigate incidents by manually digging through CloudTrail logs, cross-referencing AWS documentation, and writing reports. This is slow, error-prone, and requires deep AWS expertise. DocuGen AI automates the entire workflow. The key innovation is that reports are documentation-grounded — every finding and recommendation is backed by actual AWS documentation retrieved through RAG, not just the LLM's training data. This makes reports auditable and verifiable.

**Q: Walk me through what happens when a user submits a query.**
A: Six steps:
1. **Time Parsing** — Claude converts the natural-language time reference ("yesterday", "last Tuesday") into exact ISO-8601 timestamps by injecting the current UTC time into the prompt.
2. **Log Analysis** — The system downloads CloudTrail log files from S3 for that time range, decompresses them, filters events by exact timestamps, categorizes each event using a deterministic dictionary lookup (not LLM), extracts target resources from requestParameters, filters out noise events, and generates a Claude-powered summary.
3. **Event Filter** — Claude reads the user's question and decides which event categories are relevant (e.g., only IAM_CHANGE for an IAM question, all categories for a broad audit). Events outside the relevant categories are removed.
4. **Retrieval (RAG)** — The relevant categories are converted into a search query, embedded via Titan Embeddings, and used to search Pinecone for the most similar AWS documentation chunks. If the average similarity score (confidence) is below 0.50, the system retries with a broader query, up to 2 times.
5. **Report Synthesis** — Claude receives the filtered events, the retrieved documentation, and the confidence score, and writes a structured Markdown report with executive summary, timeline, findings, risk assessment, and recommendations. Every recommendation cites a specific doc source.
6. **Store Report** — The report and its metadata are saved to S3 for persistence and auditability.

---

## 2. ARCHITECTURE & DESIGN DECISIONS

**Q: Why did you choose a multi-agent architecture instead of a single prompt?**
A: Separation of concerns. Each agent has a single responsibility, making the system easier to test, debug, and explain. Only the Report Synthesis agent performs deep reasoning — the most expensive and hallucination-prone step. By delaying it until all data is gathered and verified, we minimize hallucination risk. Each agent can also be tested in isolation with mocked dependencies.

**Q: Why LangGraph specifically?**
A: LangGraph is designed for multi-agent workflows with shared state. The key feature we use is `add_conditional_edges()` — after retrieval, the pipeline either proceeds to report writing or loops back to retry with a broader query. You can't do this with a simple function chain — you'd need manual if/else logic. LangGraph handles it declaratively. It also manages the shared state automatically — each node returns a dict, and LangGraph merges it into the state.

**Q: Could you have built this without LangGraph?**
A: Yes, functionally. We could chain function calls and use if/else for the retry loop. But LangGraph gives us: (1) declarative graph definition that's easy to visualize and explain, (2) automatic state management — nodes just return dicts and LangGraph merges them, (3) the conditional edge pattern that makes the retry loop clean, and (4) it's a real industry tool that demonstrates familiarity with agent orchestration frameworks.

**Q: Why Amazon Bedrock instead of calling the Anthropic API directly?**
A: Keeps the entire stack AWS-native — single credential chain (AWS IAM) for all services. No separate API keys to manage for Anthropic. It also demonstrates cloud-native architecture. We access both Claude 3.5 Sonnet (text generation) and Titan Embeddings V2 (vector embeddings) through the same Bedrock service.

**Q: Why two different Bedrock APIs — converse() and invoke_model()?**
A: Bedrock offers two ways to call models. `converse()` is a standardized chat API — same message format regardless of which chat model you use. We use it for Claude. `invoke_model()` is a lower-level API that sends raw JSON — required for Titan Embeddings because it's not a chat model. It takes text in and returns numbers (vectors), which the chat API doesn't support.

**Q: Why Pinecone instead of a local vector store like FAISS?**
A: Pinecone demonstrates real vector database usage — a managed, cloud-hosted, production-grade service. FAISS would work functionally but wouldn't demonstrate cloud-native patterns. Pinecone's free tier is sufficient for our ~200 vectors. It's also accessible from any machine without local file dependencies.

**Q: Why Streamlit for the UI?**
A: Fast to build, Python-native (no frontend framework needed), built-in Markdown rendering for the reports, and has native components for spinners, download buttons, and JSON display. For a portfolio project focused on backend architecture, it gets a working UI up quickly without distracting from the core system.

---

## 3. RAG (RETRIEVAL-AUGMENTED GENERATION)

**Q: What is RAG and why do you use it?**
A: RAG stands for Retrieval-Augmented Generation. Instead of relying only on the LLM's training data (which may be outdated and can't be verified), we retrieve specific, real documents and include them in the prompt. This grounds the LLM's output in verifiable sources. An auditor can check "According to iam-best-practices.md..." against the actual document. You can't audit "According to Claude's training data..."

**Q: Walk me through how RAG works in your system.**
A: Three phases:
1. **Indexing (first run only):** We read ~12 curated AWS documentation files, split each into ~1000-character chunks with 200-character overlap, embed each chunk using Titan Embeddings V2 (→ 1024-dimension vector), and store the vectors in Pinecone with the original text in metadata. ~200 chunks total, runs once.
2. **Retrieval (every query):** The retrieval agent builds a search query from the relevant event categories (e.g., "IAM users roles policies best practices" for IAM_CHANGE events). This query is embedded into a vector, then sent to Pinecone which returns the 5 most similar document chunks with cosine similarity scores.
3. **Generation:** The retrieved doc chunks are included in the prompt to Claude alongside the events. Claude writes the report grounded in these specific documents and cites them by filename.

**Q: Why do you chunk documents instead of embedding them whole?**
A: If you embed a 4000-character document about IAM covering users, roles, policies, and best practices, the vector represents the average meaning of all those topics — too vague. When someone asks specifically about "IAM roles", that average vector won't match well. By splitting into ~1000-character chunks, each vector represents a focused topic, making similarity search more precise.

**Q: What's the 200-character overlap for?**
A: If a sentence starts at character 950 and ends at character 1050, it would get cut in half without overlap. With 200-character overlap, adjacent chunks share text at their boundaries, so the sentence appears fully in both chunks. Nothing is lost at the boundary.

**Q: What is cosine similarity?**
A: It measures how similar two vectors are by comparing the angle between them, on a scale of 0 to 1. 1.0 means identical meaning, 0.0 means completely unrelated. In our system, typical "good match" scores with Titan V2 are 0.50-0.70. We use the average score of the top 5 results as our confidence metric.

**Q: What is the confidence threshold and why is it 0.50?**
A: The confidence threshold is the minimum average cosine similarity required for retrieved documents to be considered "sufficient." We set it to 0.50 because Titan Embeddings V2 produces lower absolute scores than other embedding models — its typical range for good matches is 0.45-0.70. We calibrated this empirically by testing various queries and checking whether the returned docs were actually relevant. 0.50 consistently separated relevant from irrelevant results.

**Q: What happens if confidence is below the threshold?**
A: The system retries with a broader search query. Three levels:
- Attempt 1: Category-specific query (e.g., "IAM users roles policies best practices")
- Attempt 2: Broader security context ("AWS security best practices shared responsibility model")
- Attempt 3: Broadest possible ("AWS cloud security IAM identity access management compliance")

If confidence is still below 0.50 after all 3 attempts, the report is generated anyway but with a prominent low-confidence disclaimer at the top.

**Q: Why don't you use the user's raw question as the RAG search query?**
A: The user might ask "What happened yesterday?" — that's about time, not about any AWS topic. It would retrieve irrelevant docs. Instead, we build the search query from the event categories we found (e.g., IAM_CHANGE → "IAM users roles policies best practices"). This targets the RAG search at documentation relevant to what actually happened, not what the user literally asked.

---

## 4. CLOUDTRAIL & S3

**Q: What is CloudTrail?**
A: AWS CloudTrail is an audit logging service that automatically records every API call made in your AWS account. Every time someone creates a user, launches a server, changes a security group, or even just logs in — CloudTrail records it as an event with timestamps, who did it, from what IP, what parameters were used, etc.

**Q: How are CloudTrail logs stored?**
A: CloudTrail saves log files to S3 in a structured folder path: `AWSLogs/{account_id}/CloudTrail/{region}/YYYY/MM/DD/`. Each file is a gzip-compressed JSON containing a batch of events (not one event per file). CloudTrail delivers these batches every 5-15 minutes.

**Q: Why read from S3 instead of using the CloudTrail LookupEvents API?**
A: The LookupEvents API only covers the last 90 days and has rate limits. Reading from S3 gives full history access, better performance for bulk reads, and demonstrates a more realistic production pattern where security tools consume logs from S3.

**Q: How does your system find the right log files?**
A: Two levels of filtering:
1. **File-level:** We build S3 folder paths from the date range and list files. Each filename contains a timestamp (e.g., `T1100Z`). We extract this with regex and skip files outside the requested time range — they're never downloaded.
2. **Event-level:** Even after file-level filtering, individual events inside a file may fall slightly outside the range (batch boundaries aren't clean). The log analysis agent checks each event's individual timestamp against the exact range.

**Q: What is the S3 paginator and why do you use it?**
A: S3 returns a maximum of 1000 files per API call. If a day has more than 1000 log files, a single call would miss some. The paginator automatically makes multiple requests and yields results page by page, ensuring we get every file regardless of how many there are.

---

## 5. EVENT PROCESSING

**Q: How do you categorize events?**
A: Deterministic dictionary lookup — not LLM-based. We have a predefined dictionary mapping CloudTrail event names to categories: CreateUser → IAM_CHANGE, ConsoleLogin → AUTH_EVENT, CreateSecurityGroup → SECURITY_GROUP, etc. If an event name isn't in any list, it gets categorized as "OTHER". This is fast, reliable, and predictable — no API calls, no potential for hallucination.

**Q: Why not use the LLM for categorization?**
A: There's no need for AI on a simple classification task. The mapping between event names and categories is well-defined and finite. Using an LLM would add latency, cost, and unpredictability for zero benefit. We save the LLM for tasks that actually need reasoning — summarization, category selection, and report writing.

**Q: What are noise events and why filter them?**
A: AWS services constantly perform routine background operations — checking bucket permissions (GetBucketAcl), generating encryption keys (GenerateDataKey), listing buckets (ListBuckets), etc. These generate hundreds of events per day that are real but not security-relevant. In a typical day: ~20 significant events, ~800+ noise events. Without filtering, the noise would overwhelm the summary and report. We don't delete them — they're moved to the end of the event list for completeness.

**Q: What's the difference between userName and targetResource?**
A: `userName` (from `userIdentity`) tells us WHO performed the action. `targetResource` (from `requestParameters`) tells us WHAT was acted upon. For example, when docugen-dev creates a new user called test-final-user: userName = "docugen-dev", targetResource = "test-final-user". Without this distinction, the report might say "docugen-dev was created" instead of "test-final-user was created by docugen-dev."

**Q: Why is the Event Filter a separate step from Log Analysis?**
A: Log Analysis is about data collection — it gathers everything objectively. Event Filter is about question interpretation — it makes a subjective judgment about relevance using the LLM. Keeping them separate means: (1) Log Analysis can be reused with different filtering strategies, (2) each step can be tested independently, (3) clear separation of concerns — collection vs. interpretation.

**Q: How does the Event Filter work?**
A: It sends Claude the user's question along with the list of categories found in the events and descriptions of what each category means. Claude returns just the relevant category names (e.g., "IAM_CHANGE" for an IAM question, or all categories for "give me a full security audit"). Events not in the selected categories are removed. The cost is ~100 tokens, ~2-3 seconds. We chose this approach (Option B) over sending everything (unfocused RAG) or query-biased search (only biases ranking, doesn't exclude).

---

## 6. REPORT GENERATION

**Q: How does the report agent produce grounded reports?**
A: The prompt includes: (1) the user's original question, (2) the filtered events with timestamps, users, IPs, and target resources, (3) the retrieved AWS documentation chunks with source filenames, and (4) the confidence score. The system prompt instructs Claude to reference specific events by name/timestamp, cite documentation sources by filename, and include a disclaimer if confidence is low. This makes every claim in the report traceable to either a real event or a real document.

**Q: How do you prevent the report from being dominated by one event category?**
A: Instead of sending the first 30 events (which might all be IAM events), we select up to 5 events per category. This ensures that if there are IAM, Security Group, and S3 events, all three categories appear in the report. Events are then sorted chronologically for a coherent timeline.

**Q: What's in the report metadata?**
A: Report ID (UUID), original query, time range analyzed, generation timestamp, model used (Claude 3.5 Sonnet), retrieval confidence score, list of documentation sources referenced, and total event count. This metadata is stored alongside the report in S3 and displayed in a collapsible panel in the Streamlit UI.

---

## 7. INFRASTRUCTURE & SERVICES

**Q: What is the singleton pattern you use in your service files?**
A: Every service file (bedrock_llm.py, bedrock_embeddings.py, s3_client.py, pinecone_client.py) creates its client connection once and reuses it. The first call to get_client() creates the AWS/Pinecone connection and stores it in a module-level variable. Every subsequent call returns the same connection. Without this, every LLM call or S3 download would create a new connection — slow and wasteful, especially during indexing (~200 Titan API calls).

**Q: Why do you use temperature 0.0 for Claude?**
A: Deterministic output — same input produces the same output. This is important for time parsing (consistent date interpretation), category selection (reliable comma-separated lists), and reproducibility (running the same query twice should produce similar reports).

**Q: What is normalize=True in your embedding calls?**
A: Normalization scales vectors to unit length (magnitude = 1). This is required for cosine similarity to work correctly. Without it, a longer text would produce a "bigger" vector and appear "more similar" to everything just because it's bigger — not because the meaning is closer. Normalization removes that size bias.

**Q: How is the first-run indexing triggered?**
A: `graph.py`'s `build_graph()` function calls `index_documents()` before constructing the pipeline. `index_documents()` checks if Pinecone already has vectors via `describe_index_stats()`. If the count is 0, it reads all docs, chunks them, embeds them, and uploads to Pinecone (~1-2 minutes). On every subsequent run, the check returns >0 and indexing is skipped in ~1 second.

---

## 8. TESTING

**Q: How do you test a system that depends on AWS and Pinecone?**
A: All external services are mocked using Python's `unittest.mock.patch`. We mock at the agent level — patching `agents.time_parsing.invoke_claude`, `agents.log_analysis.invoke_claude`, etc. This lets us test each agent's logic without making real API calls. We have unit tests for each agent and an integration test that runs the full pipeline with all services mocked.

**Q: What does the integration test verify?**
A: It mocks all 4 Claude calls (time parsing, event summary, category filter, report generation), the S3 file listing/reading, the Pinecone query, and the S3 report storage. Then it runs `run_pipeline("What IAM changes happened last Tuesday?")` and verifies: (1) the final report is not None and contains expected content, (2) the metadata includes the correct event count, (3) the retrieval confidence is above threshold.

**Q: What test scenarios do you cover?**
A: For each agent: valid inputs produce correct outputs, edge cases are handled (e.g., unknown event names → "OTHER" category, no events found → empty list). For the pipeline: specific queries (IAM only), broad queries (full security audit), time parsing with various natural-language references. We tested with real AWS activity — created IAM users, security groups, S3 buckets, then queried for each.

---

## 9. SCALING & IMPROVEMENTS

**Q: How does the system scale?**
A: Currently designed for single-account, single-region use. For scaling: (1) multiple CloudTrail trails could be aggregated into the same S3 bucket, (2) the Pinecone index could be expanded with more documentation and multiple namespaces, (3) the Streamlit UI could be replaced with a production web framework, (4) agent calls could be parallelized where independent (e.g., retrieval doesn't depend on the event summary).

**Q: What's the latency of a typical query?**
A: Approximately 30-60 seconds. The bottleneck is the 4 Claude API calls through Bedrock (~5-10 seconds each). Potential optimizations: caching time parsing results for common phrases, pre-computing event summaries for recent days, or parallelizing the event summary and event filter calls since they're independent.

**Q: What would you change if you built this again?**
A: (1) Add streaming for the report generation so the user sees output progressively instead of waiting 30+ seconds. (2) Add error handling for individual agent failures with meaningful user-facing messages. (3) Consider a persistent conversation history so users can ask follow-up questions about a report. (4) Add support for multi-region and multi-account CloudTrail analysis.

**Q: What happens if Bedrock or Pinecone goes down?**
A: Currently, the pipeline would fail and Streamlit would show a generic error. In production, you'd add: (1) retry logic with exponential backoff for transient API failures, (2) circuit breakers to avoid hammering a down service, (3) graceful degradation — e.g., if Pinecone is down, generate a report without RAG grounding but with a clear disclaimer.

---

## 10. CODE-SPECIFIC QUESTIONS

**Q: What does `json.dumps()` do vs `json.loads()`?**
A: `json.dumps()` converts a Python dict/list into a JSON string (Python → string). `json.loads()` converts a JSON string back into a Python dict/list (string → Python). We use `dumps()` when sending data to APIs (they expect JSON strings), and `loads()` when receiving data back (APIs return JSON strings that we need as Python dicts).

**Q: What does the `global` keyword do in your get_client() functions?**
A: Without `global`, writing `_client = boto3.client(...)` inside the function would create a local variable called `_client` that disappears when the function ends. `global _client` tells Python "I'm talking about the `_client` at the top of the file, not a new local one." This is how the singleton pattern works — the variable persists at the module level.

**Q: What is `boto3`?**
A: The official AWS SDK for Python. It lets Python code talk to any AWS service — S3, Bedrock, IAM, EC2, CloudTrail, etc. In our system, we use it to create clients for S3 (read logs, store reports) and Bedrock Runtime (call Claude and Titan models).

**Q: What does `graph.compile()` do?**
A: It takes all the nodes and edges we defined (with `add_node`, `add_edge`, `add_conditional_edges`) and turns them into a runnable application. Before compile, we have a graph definition. After compile, we have an object we can call `.invoke()` on to actually run the pipeline.

**Q: What does `app.invoke(initial_state)` do?**
A: It starts the pipeline at the entry point node (time_parsing), passes the initial state through, and runs each node in order following the edges. Each node reads from the state, does its work, and returns updates that LangGraph merges back into the state. When it reaches END, invoke() returns the final state with all fields filled in.

**Q: What is `RecursiveCharacterTextSplitter`?**
A: A text splitter from LangChain that breaks documents into chunks of a specified size. "Recursive" means it tries to split at natural boundaries first — paragraph breaks (\n\n), then line breaks (\n), then spaces, then individual characters. So it won't cut a sentence in half if it can avoid it. We use it with chunk_size=1000 and chunk_overlap=200.

**Q: Why do you use `Optional` in the state types?**
A: `Optional` means "this field can be None." At the start of the pipeline, only `query` has a value — everything else is None because no agent has run yet. As each agent runs, it fills in its fields. By the end, everything is populated. Without Optional, Python's type checker would complain about None values in the initial state.
