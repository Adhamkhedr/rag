"""
LangGraph Pipeline — The Assembly Line
========================================
If state.py is the shared notebook, this file is the ASSEMBLY LINE that
decides which agent gets the notebook next.

This file does two things:
    1. build_graph() — Defines the order agents run in, including the
       conditional retry loop for retrieval confidence.
    2. run_pipeline() — Creates the initial empty state, starts the
       pipeline, and returns the final filled-in state.

What is LangGraph?
    LangGraph is a framework for building multi-agent pipelines. Instead
    of manually calling functions one after another like:
        result1 = time_parsing(state)
        result2 = log_analysis(result1)
        result3 = retrieval(result2)
        ...
    You define a GRAPH of nodes (agents) and edges (connections), and
    LangGraph handles running them in order, passing the shared state
    between them, and handling conditional branching (like our retry loop).

    The key advantage: conditional logic. Our pipeline isn't a straight
    line — after retrieval, it either continues to report writing OR loops
    back to retry. LangGraph handles this with add_conditional_edges().

Three LangGraph concepts used here:
    1. NODE — A function that reads from state, does work, returns updates.
       Each of our agents is a node.
    2. EDGE — A connection saying "after node A finishes, run node B next."
    3. CONDITIONAL EDGE — A connection that picks the next node based on
       a function's return value (like an if/else for the pipeline).

The pipeline flow:
    time_parsing → log_analysis → event_filter → retrieval
                                                     ↓
                                              confidence_check
                                               ↙          ↘
                                          "retry"      "sufficient"
                                             ↓              ↓
                                      increment_retry   report_synthesis
                                             ↓              ↓
                                          retrieval     store_report
                                          (try again)       ↓
                                                           END
"""

from langgraph.graph import StateGraph, END
# StateGraph: the LangGraph class for building a graph of nodes and edges
# END: a special constant that marks the end of the pipeline

from state import DocuGenState
# The shared state definition — tells LangGraph what fields the state has

from agents.time_parsing import time_parsing_node
from agents.log_analysis import log_analysis_node, event_filter_node
from agents.retrieval import retrieval_node, confidence_check, increment_retry
from agents.report_synthesis import report_synthesis_node, store_report_node
# All the agent functions that will be registered as nodes

from services.indexer import index_documents
# First-run doc indexing — called once before the pipeline runs


def build_graph():
    """Construct and compile the DocuGen AI LangGraph pipeline.

    This function:
    1. Ensures docs are indexed in Pinecone (skips if already done)
    2. Creates a StateGraph with our DocuGenState shape
    3. Registers all agent functions as nodes
    4. Connects them with edges (including the conditional retry loop)
    5. Compiles the graph into a runnable application

    Returns a compiled LangGraph app that can be invoked with .invoke().
    """
    # --- Step 1: Ensure docs are indexed ---
    # index_documents() checks if Pinecone already has vectors.
    # First run: indexes all AWS docs (~1-2 minutes).
    # Every run after: skips in ~1 second (already indexed).
    index_documents()

    # --- Step 2: Create the graph ---
    # StateGraph(DocuGenState) tells LangGraph: "the shared state that
    # flows between nodes has these fields" (query, time_range, etc.)
    graph = StateGraph(DocuGenState)

    # --- Step 3: Register all nodes (agents) ---
    # add_node("name", function) says: "here's a worker called 'name',
    # and this is the function it runs."
    # At this point they're just registered — not connected yet.
    graph.add_node("time_parsing", time_parsing_node)       # Step 1: NL time → ISO-8601
    graph.add_node("log_analysis", log_analysis_node)       # Step 2: Download & categorize logs
    graph.add_node("event_filter", event_filter_node)       # Step 3: Filter by question relevance
    graph.add_node("retrieval", retrieval_node)             # Step 4: RAG search in Pinecone
    graph.add_node("increment_retry", increment_retry)      # Step 5: Bump retry count by 1
    graph.add_node("report_synthesis", report_synthesis_node)  # Step 6: Write the report
    graph.add_node("store_report", store_report_node)       # Step 7: Save report to S3

    # --- Step 4: Connect nodes with edges ---

    # Linear edges — a straight line from start to retrieval.
    # set_entry_point tells LangGraph which node runs FIRST.
    graph.set_entry_point("time_parsing")
    graph.add_edge("time_parsing", "log_analysis")   # After time parsing → do log analysis
    graph.add_edge("log_analysis", "event_filter")   # After log analysis → filter by question
    graph.add_edge("event_filter", "retrieval")      # After filtering → search for relevant docs

    # Conditional edge — THE KEY LANGGRAPH FEATURE.
    # After retrieval runs, instead of always going to the same next node,
    # LangGraph calls the confidence_check function. This function looks at
    # the state and returns a string:
    #   - "sufficient" → confidence >= 0.50 OR we've used all retries
    #                     → go to report_synthesis (write the report)
    #   - "retry"      → confidence < 0.50 AND retries left
    #                     → go to increment_retry (try again with broader query)
    #
    # This is like an if/else inside the pipeline. You can't do this with
    # a simple chain of function calls — you'd need manual if/else logic.
    # LangGraph handles it declaratively.
    graph.add_conditional_edges(
        "retrieval",          # After this node finishes...
        confidence_check,     # ...call this function to decide what's next
        {
            "sufficient": "report_synthesis",   # If it returns "sufficient" → go here
            "retry": "increment_retry",         # If it returns "retry" → go here
        },
    )

    # Retry loop — increment_retry bumps retry_count by 1, then goes back
    # to retrieval. Retrieval will use a BROADER search query on each retry.
    # This can happen up to 2 times (MAX_RETRIES from config.py).
    # After 2 retries, confidence_check returns "sufficient" regardless
    # (better to write a report with a low-confidence warning than to
    # loop forever).
    graph.add_edge("increment_retry", "retrieval")

    # Final edges — after the report is written, save it to S3, then stop.
    graph.add_edge("report_synthesis", "store_report")
    graph.add_edge("store_report", END)  # END is a LangGraph constant meaning "pipeline done"

    # --- Step 5: Compile the graph ---
    # compile() takes all the nodes and edges we defined above and turns
    # them into a runnable application. After this, we can call .invoke()
    # on it to run the entire pipeline.
    return graph.compile()


def run_pipeline(query: str) -> DocuGenState:
    """Run the full DocuGen AI pipeline with a user query. Returns final state.

    This is the function that app.py (Streamlit) calls. It:
    1. Builds the graph (registers nodes, connects edges, compiles)
    2. Creates the initial state with only "query" filled in
    3. Calls app.invoke() which runs the pipeline from start to END
    4. Returns the final state with everything filled in

    Args:
        query: The user's natural-language question.
               Example: "What IAM changes happened yesterday?"

    Returns:
        The final DocuGenState with all fields populated:
        time_range, log_findings, retrieved_docs, final_report, etc.
    """
    app = build_graph()

    # The initial state — only "query" has a real value.
    # Everything else starts as None or 0.
    # As each node runs, it fills in its fields, and LangGraph merges
    # the updates into this state automatically.
    initial_state = {
        "query": query,                  # The user's question
        "time_range": None,              # Step 1 will fill this
        "log_findings": None,            # Step 2 will fill this
        "relevant_categories": None,     # Step 3 will fill this
        "retrieved_docs": None,          # Step 4 will fill this
        "retrieval_confidence": 0.0,     # Step 4 will update this
        "retry_count": 0,               # Step 5 increments this on retries
        "final_report": None,           # Step 6 will fill this
        "metadata": None,              # Step 6 will fill this
    }

    # invoke() starts the pipeline at the entry point (time_parsing)
    # and runs through every node, following edges, until it reaches END.
    # The return value is the final state dict with everything filled in.
    return app.invoke(initial_state)
