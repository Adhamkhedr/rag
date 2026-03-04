"""
Document Indexer — First-Run AWS Documentation Indexing
========================================================
This service runs ONCE on the first app launch, then never again (unless
the Pinecone index is cleared). It reads all curated AWS documentation
files from docs/aws/, splits them into chunks, embeds each chunk using
Titan Embeddings, and uploads the vectors to Pinecone.

Why this is needed:
    RAG (Retrieval-Augmented Generation) requires a searchable knowledge
    base. The raw .md files on disk can't be searched by semantic similarity
    — they need to be converted into vectors first. This indexer does that
    one-time conversion.

How it works, step by step:
    1. Check if Pinecone already has data → if yes, skip everything
    2. List all .md files in docs/aws/ (sorted alphabetically)
    3. For each file:
       a. Read the full text content
       b. Split into chunks of 1000 chars with 200-char overlap
       c. Embed each chunk using Titan Embeddings (→ 1024-dim vector)
       d. Package as {id, values, metadata} for Pinecone
    4. Upsert all vectors to Pinecone in batches of 100

Why chunking is needed:
    Our AWS docs are 2000-5000 characters each. If we embedded entire
    documents, the vector would represent the "average meaning" of the
    whole doc — too vague for precise retrieval. By splitting into ~1000
    char chunks, each vector represents a focused topic, making similarity
    search more precise.

Why 200-char overlap:
    If a sentence spans the boundary between two chunks, the overlap
    ensures it appears in both chunks. Without overlap, you could lose
    important information at chunk boundaries.

    Example with a 1000-char chunk and 200-char overlap:
        Chunk 0: characters 0-999
        Chunk 1: characters 800-1799    (overlaps with chunk 0 by 200 chars)
        Chunk 2: characters 1600-2599   (overlaps with chunk 1 by 200 chars)

Why metadata stores the full text:
    Each Pinecone vector stores the original chunk text in its metadata.
    This means when we query Pinecone later, we get the text back directly
    — no need to re-read the file from disk and figure out which chunk
    matched. This is faster and simpler.

When this runs:
    Called by build_graph() in graph.py, which runs when the app starts.
    The index_has_data() check makes it a no-op on subsequent runs.

Performance:
    ~12 doc files → ~200 chunks → ~200 Titan API calls → ~1-2 minutes
    Only happens once. After that, the vectors persist in Pinecone.
"""

import os
from langchain_text_splitters import RecursiveCharacterTextSplitter
from services.bedrock_embeddings import embed_text
from services.pinecone_client import upsert_vectors, index_has_data
from config import DOCS_DIR, CHUNK_SIZE, CHUNK_OVERLAP


def index_documents():
    """Index all AWS docs into Pinecone. Skips if the index already has data.

    This is the main entry point. Called once from graph.py at startup.
    Subsequent calls are no-ops thanks to the index_has_data() check.
    """
    # Step 1: Check if Pinecone already has vectors.
    # If yes, indexing was already done in a previous run — skip.
    if index_has_data():
        print("Pinecone index already contains data. Skipping indexing.")
        return

    print("First run detected. Indexing AWS documentation into Pinecone...")

    # Step 2: Create a text splitter from LangChain.
    # RecursiveCharacterTextSplitter tries to split at natural boundaries
    # (paragraphs, sentences, words) rather than cutting mid-word.
    # "Recursive" means it tries the largest separator first (\n\n),
    # then falls back to smaller ones (\n, space, character).
    #
    # chunk_size=1000: Each chunk is at most 1000 characters (~200 words)
    # chunk_overlap=200: Adjacent chunks share 200 characters at boundaries
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    """Why not embed entire documents? Say you have a 4000-character doc about IAM that covers    
  users, roles, policies, and best practices. If you embed the whole thing, the vector       
  represents the average meaning of all those topics — too vague. When someone asks about    
  "IAM roles" specifically, that average vector won't match well."""

    vectors = []

    # Step 3: List all .md files in the docs/aws/ directory, sorted
    # alphabetically for deterministic ordering.
    doc_files = sorted(f for f in os.listdir(DOCS_DIR) if f.endswith(".md"))

    for filename in doc_files:
        # Step 3a: Read the full text content of the file.
        filepath = os.path.join(DOCS_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Step 3b: Split the document into chunks.
        # A 3000-char doc with 1000-char chunks and 200-char overlap
        # produces roughly 4 chunks.
        chunks = splitter.split_text(content)
        print(f"  {filename}: {len(chunks)} chunks")

        for i, chunk in enumerate(chunks):
            # Step 3c: Create a unique ID for this chunk.
            # Format: "filename::chunk-N"
            # Example: "iam-users-guide.md::chunk-3"
            # This ID is used by Pinecone to identify the vector.
            # If we re-index, upsert will overwrite vectors with the same ID.
            vector_id = f"{filename}::chunk-{i}"

            # Step 3d: Embed the chunk text using Titan Embeddings.
            # This converts the text into a 1024-dimension vector.
            # This is the slowest step — each call takes ~0.5-1 second.
            embedding = embed_text(chunk)

            # Step 3e: Package the vector for Pinecone.
            # - id: unique identifier
            # - values: the 1024-dim embedding vector
            # - metadata: stored alongside the vector in Pinecone
            #     - content: the original text (so we can retrieve it later
            #       without re-reading the file)
            #     - source: which file this came from (cited in reports)
            #     - chunk_index: position in the document (for ordering)
            vectors.append({
                "id": vector_id,
                "values": embedding,
                "metadata": {
                    "content": chunk,
                    "source": filename,
                    "chunk_index": i,
                },
            })

    # Step 4: Upload all vectors to Pinecone.
    # upsert_vectors() handles batching (100 per request).
    upsert_vectors(vectors)
    print(f"Indexed {len(vectors)} chunks from {len(doc_files)} documents.")
