"""
Pinecone Client Service — Vector Database Operations
======================================================
This service handles all communication with Pinecone, the vector database
where our embedded AWS documentation chunks are stored.

What is Pinecone?
    A cloud-hosted vector database. It stores vectors (lists of numbers)
    and lets you search for the most similar ones. In our system:
    - Each vector represents an AWS documentation chunk
    - Each vector has 1024 dimensions (from Titan Embeddings)
    - Each vector has metadata attached (the original text + source filename)

How it's used in the pipeline:
    1. INDEXING (first run): The indexer embeds each doc chunk and calls
       upsert_vectors() to store them in Pinecone.
    2. RETRIEVAL (every query): The retrieval agent embeds the search query
       and calls query_vectors() to find the 5 most similar doc chunks.
    3. FIRST-RUN CHECK: index_has_data() checks if vectors exist to decide
       whether to run the indexer.

Why Pinecone (not a local vector DB like FAISS)?
    - Cloud-hosted: no local storage needed, works from any machine
    - Free tier is sufficient for our ~200 vectors
    - Managed service: no maintenance, automatic scaling
    - Demonstrates cloud-native architecture for the portfolio

Index configuration (set up via Pinecone dashboard, not in code):
    - Index name: "docugen-aws-docs"
    - Dimensions: 1024 (must match Titan V2 output)
    - Metric: cosine (measures angle between vectors, not distance)
    - Single namespace (no partitioning needed for ~200 vectors)

Singleton pattern:
    The Pinecone index connection is created once and reused.
"""

from pinecone import Pinecone
from config import PINECONE_API_KEY, PINECONE_INDEX_NAME

# ---------------------------------------------------------------------------
# Singleton Pinecone index reference.
# Created once on first call to get_index(), then reused.
# ---------------------------------------------------------------------------
_index = None


def get_index():
    """Return the shared Pinecone index, creating the connection on first call.

    Two steps:
    1. Pinecone(api_key=...) — authenticates with the Pinecone service
    2. pc.Index(name) — gets a reference to our specific index

    The index reference is stored in _index and reused for all operations.
    """
    global _index
    if _index is None:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        _index = pc.Index(PINECONE_INDEX_NAME)
    return _index


def upsert_vectors(vectors: list[dict]):
    """Upload vectors to Pinecone. Used during first-run indexing.

    "Upsert" means "insert or update" — if a vector with the same ID
    already exists, it gets overwritten. This makes re-indexing safe.

    Vectors are sent in batches of 100 because Pinecone has per-request
    size limits. For ~200 vectors, this means 2 API calls.

    Args:
        vectors: List of dicts, each with:
            - "id": Unique identifier (e.g., "iam-users-guide.md::chunk-3")
            - "values": List of 1024 floats (the embedding)
            - "metadata": Dict with "content" (original text), "source"
              (filename), and "chunk_index" (position in the document)

    The metadata is stored IN Pinecone alongside the vector. This is a
    key design decision — it means we can retrieve the original text
    directly from Pinecone without needing to re-read the file from disk.
    """
    index = get_index()
    batch_size = 100
    for i in range(0, len(vectors), batch_size):
        batch = vectors[i : i + batch_size]
        index.upsert(vectors=batch)


def query_vectors(vector: list[float], top_k: int = 5) -> list[dict]:
    """Search Pinecone for the most similar document chunks. This is the RAG search.

    Takes a query vector (the embedded search query from the retrieval agent)
    and finds the top-K most similar vectors in the index using cosine
    similarity. Returns the matching chunks with their similarity scores.

    How cosine similarity works:
        - Measures the angle between two vectors (0 to 1 scale)
        - 1.0 = identical meaning
        - 0.0 = completely unrelated
        - Typical "good match" scores with Titan V2: 0.50-0.70

    Args:
        vector: The query embedding (1024 floats from embed_text())
        top_k:  How many results to return (default 5, from config.TOP_K)

    Returns:
        List of dicts, each with:
            - "content": The original text chunk (from metadata)
            - "source": Which .md file it came from (e.g., "iam-users-guide.md")
            - "similarity": Cosine similarity score (0 to 1)

        Results are ordered by similarity (highest first).
    """
    index = get_index()

    # include_metadata=True tells Pinecone to return the stored metadata
    # (content and source) alongside each match, not just the vector ID.
    results = index.query(vector=vector, top_k=top_k, include_metadata=True)

    # Transform Pinecone's response format into our simpler format.
    # Pinecone returns: {"matches": [{"id": "...", "score": 0.85, "metadata": {...}}, ...]}
    # We return: [{"content": "...", "source": "...", "similarity": 0.85}, ...]
    return [
        {
            "content": m["metadata"]["content"],
            "source": m["metadata"]["source"],
            "similarity": m["score"],
        }
        for m in results["matches"]
    ]


def index_has_data() -> bool:
    """Check if the Pinecone index already contains vectors.

    Used by the indexer to decide whether to run first-time indexing.
    If total_vector_count > 0, the docs are already indexed and we skip.

    describe_index_stats() returns metadata about the index including
    the total number of vectors stored.
    """
    index = get_index()
    stats = index.describe_index_stats()
    return stats["total_vector_count"] > 0
