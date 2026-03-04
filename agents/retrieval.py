from services.bedrock_embeddings import embed_text
from services.pinecone_client import query_vectors
from state import DocuGenState
from config import TOP_K, CONFIDENCE_THRESHOLD, MAX_RETRIES


def build_retrieval_query(state: DocuGenState) -> str:
    """Build a search query from log findings. Broadens on each retry."""
    events = state["log_findings"]["events"]
    retry_count = state.get("retry_count", 0)

    # Use only the relevant categories (filtered by event_filter_node)
    # Fall back to all categories if relevant_categories isn't set
    if state.get("relevant_categories"):
        categories = state["relevant_categories"]
    else:
        categories = list(set(e["category"] for e in events))

    # Map categories to natural-language doc-style queries
    category_queries = {
        "IAM_CHANGE": "IAM users roles policies best practices least privilege credentials",
        "AUTH_EVENT": "AWS console login authentication MFA access keys session",
        "SECURITY_GROUP": "EC2 security groups inbound outbound rules network access",
        "S3_CONFIG": "S3 bucket policies access control public access encryption",
        "EC2_LIFECYCLE": "EC2 instances launch terminate security key pairs",
        "CLOUDTRAIL_CONFIG": "CloudTrail logging monitoring trail configuration",
    }

    if retry_count == 0:
        # First attempt: category-specific natural language
        cat_queries = [category_queries.get(c, "") for c in categories if c != "OTHER"]
        query = " ".join(cat_queries) if cat_queries else "AWS security monitoring and access management"
    elif retry_count == 1:
        # Second attempt: broader security context
        query = "AWS security best practices shared responsibility model monitoring access control"
    else:
        # Third attempt: broadest
        query = "AWS cloud security IAM identity access management incident response compliance"

    return query


def retrieval_node(state: DocuGenState) -> dict:
    """LangGraph node: retrieve relevant AWS docs from Pinecone."""
    query_text = build_retrieval_query(state)
    query_vector = embed_text(query_text)
    results = query_vectors(query_vector, top_k=TOP_K)

    if results:
        confidence = sum(r["similarity"] for r in results) / len(results)
    else:
        confidence = 0.0

    return {
        "retrieved_docs": results,
        "retrieval_confidence": confidence,
    }


def confidence_check(state: DocuGenState) -> str:
    """LangGraph conditional edge: decide whether to retry retrieval or proceed."""
    if state["retrieval_confidence"] >= CONFIDENCE_THRESHOLD:
        return "sufficient"
    elif state.get("retry_count", 0) < MAX_RETRIES:
        return "retry"
    else:
        return "sufficient"  # Max retries reached, proceed with warning


def increment_retry(state: DocuGenState) -> dict:
    """LangGraph node: increment the retry counter before re-querying."""
    return {"retry_count": state.get("retry_count", 0) + 1}
