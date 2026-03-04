"""
Bedrock Embeddings Service — Amazon Titan Embeddings V2 Wrapper
================================================================
This service converts text into numerical vectors (embeddings) using
Amazon Titan Embeddings V2 via Bedrock. These vectors are the foundation
of RAG (Retrieval-Augmented Generation).

What is an embedding?
    A way to represent text as a list of numbers (a "vector"). Similar text
    produces similar vectors. For example:
        - "IAM user creation" → [0.23, 0.87, -0.12, ...]  (1024 numbers)
        - "Creating a new IAM identity" → [0.25, 0.85, -0.10, ...]  (very similar!)
        - "S3 bucket policies" → [0.71, -0.33, 0.55, ...]  (very different)

    By comparing vectors using cosine similarity, we can find which document
    chunks are most relevant to a search query — without keyword matching.

How it's used in the pipeline:
    1. INDEXING (first run only): Each AWS doc chunk is embedded and stored
       in Pinecone alongside its text. (~200 chunks, runs once)
    2. RETRIEVAL (every query): The search query is embedded, then compared
       against all stored vectors to find the most similar doc chunks.

Why invoke_model() instead of converse():
    The Converse API only works with chat/text models. Titan Embeddings is
    an embedding model (it produces vectors, not text), so it uses the
    lower-level invoke_model() API which sends raw JSON.

Why normalize=True:
    Normalization scales vectors to unit length (magnitude = 1). This is
    required for cosine similarity to work correctly — without it, longer
    texts would have larger vectors and appear "more similar" regardless
    of actual semantic meaning.

Singleton pattern:
    Same as bedrock_llm.py — the boto3 client is created once and reused.
"""

import boto3   
"""boto3 is the official Python SDK for AWS. In plain words:
boto3 lets Python code talk to AWS services (S3, EC2, IAM, Lambda, Bedrock, DynamoDB… you name it). """
import json   # For converting Python dicts to JSON strings and back
from config import AWS_REGION, TITAN_EMBED_MODEL_ID, EMBEDDING_DIMENSION

# ---------------------------------------------------------------------------
# Singleton boto3 client
#
# Every time we want to talk to Bedrock (to embed text), we need an AWS
# connection — that's what boto3.client("bedrock-runtime") creates.
# Creating a connection takes time (authentication, network setup, etc.).
#
# Problem: our pipeline calls embed_text() hundreds of times during
# indexing. If every call created a new connection, that's hundreds of
# unnecessary connections — slow and wasteful.
#
# Solution: create the connection ONCE, save it in _client, reuse it forever.
# This is called the "singleton pattern" — only one instance ever exists.
# ---------------------------------------------------------------------------

# Start with no connection. None means "no connection created yet".
_client = None


def get_client():
    """Return the shared Bedrock Runtime client, creating it on first call.

    What happens in practice:
        1st call:  _client is None → creates connection → saves it → returns it
        2nd call:  _client is NOT None → skips creation → returns same connection
        100th call: same — just returns the existing connection

    The "global _client" line is a Python requirement. Without it, writing
    _client = boto3.client(...) inside this function would create a LOCAL
    variable called _client that disappears when the function ends. "global"
    tells Python: "I'm talking about the _client at the top of the file,
    not a new local one."
    """
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    return _client


def embed_text(text: str) -> list[float]:
    """Generate a 1024-dimension embedding vector for a single text string.

    Takes a text string (e.g., a document chunk or a search query) and
    returns a list of 1024 floating-point numbers representing its
    semantic meaning.

    Args:
        text: The text to embed. Can be a document chunk (during indexing)
              or a search query (during retrieval).

    Returns:
        A list of 1024 floats — the embedding vector.
    """
    client = get_client()   #Gets the AWS connection (the singleton we just talked about). 

   
    response = client.invoke_model(
        modelId=TITAN_EMBED_MODEL_ID,
        body=json.dumps({
            "inputText": text,
            "dimensions": EMBEDDING_DIMENSION,
            "normalize": True,
        }),
    )
    """ This sends a request to Titan Embeddings on Bedrock. We're saying:
    - modelId — which model to use (Titan Embed V2)
    - inputText — the text we want to convert to numbers (e.g., "IAM users can be created via  
    the console")
    - dimensions — we want 1024 numbers back
    - normalize — make all vectors the same "length" so comparison is fair. Think of it like   
    this: without normalization, a 500-word chunk might produce a "bigger" vector than a       
    50-word chunk, and it would look "more similar" to everything just because it's bigger —   
    not because the meaning is closer. Normalization removes that size bias."""

    """invoke_model() is a function from the boto3 AWS SDK. 
    It's how you send data to any AI model hosted on Bedrock and get a response back.                                                                                                                                         
    Think of it like this:                                                                                                                                                                  
    - Bedrock is a building with many AI models inside (Claude, Titan, Llama, etc.)              - invoke_model() is you knocking on a specific model's door, handing it some input, and
    getting output back                                                                        
    
    It takes two main things:
    - modelId — which model's door to knock on (in our case, Titan Embeddings)
    - body — the input to give the model (in our case, the text we want converted to numbers)  

    Why do we have two different ways to call models?

    Bedrock gives you two options:

    1. invoke_model() — the general-purpose, low-level way. Works with ANY model on Bedrock.   
    You send raw JSON, you get raw JSON back. You have to know the exact format each model     
    expects.
    2. converse() — a higher-level, chat-specific way. Only works with chat models (like       
    Claude). It has a nice standardized format with messages, system, role, etc. — same format 
    regardless of which chat model you use.

    We use converse() for Claude (in bedrock_llm.py) because Claude is a chat model and        
    converse() is cleaner for chat.

    We use invoke_model() for Titan Embeddings (in this file) because Titan Embeddings is not a
    chat model — it doesn't have conversations. It just takes text in and gives numbers out.  
    converse() doesn't support that, so we use the lower-level invoke_model()."""


   
    result = json.loads(response["body"].read())
    return result["embedding"]
"""Bedrock sends the response as a stream of raw bytes (not a Python dict). So:
  1. .read() — reads the raw bytes from the stream
  2. json.loads() — converts those bytes from a JSON string back into a Python dict
  3. result["embedding"] — grabs the actual list of 1024 numbers from the dict"""

def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts sequentially. Returns a list of embedding vectors.

    Titan V2 does NOT support batch embedding (you can't send 10 texts in
    one API call), so we embed them one at a time in a loop.

    This is only used during first-run indexing (~200 chunks = ~1-2 minutes).
    During normal query processing, we only embed one search query at a time,
    so we use embed_text() directly.
    """
    return [embed_text(t) for t in texts]
