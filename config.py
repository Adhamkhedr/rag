"""
Configuration (Single Source of Truth)
=======================================
Every service and agent imports its settings from this file instead of
hardcoding them. This means if you ever need to change the AWS region,
model ID, confidence threshold, or any other setting, you change it in
ONE place and it propagates everywhere.

This file loads sensitive values (API keys) from environment variables
(set in a .env file), while non-sensitive constants are defined directly.

What each section controls:
    AWS         — Region and account ID for all AWS service calls
    Bedrock     — Which AI models to use (Claude for text, Titan for embeddings)
    S3          — Bucket names and folder paths for CloudTrail logs and reports
    Pinecone    — Vector database connection settings
    RAG         — Retrieval parameters (confidence threshold, chunk sizes, etc.)
    Docs        — Path to the curated AWS documentation files
"""

import os
from dotenv import load_dotenv

# Load environment variables from a .env file in the project root.
# This is where sensitive values like PINECONE_API_KEY are stored.
# The .env file is in .gitignore so it never gets committed to version control.
load_dotenv()

# ---------------------------------------------------------------------------
# AWS Settings
# ---------------------------------------------------------------------------
# AWS_DEFAULT_REGION: Which AWS data center to use. Defaults to us-east-1
# if not set in the environment. All services (Bedrock, S3, CloudTrail)
# must be in the same region.
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

# Our AWS account ID — used to build S3 bucket names and CloudTrail paths.
ACCOUNT_ID = "523761210523"

# ---------------------------------------------------------------------------
# Bedrock Model Settings
# ---------------------------------------------------------------------------
# CLAUDE_MODEL_ID: The exact model version of Claude we use for all text
# generation (time parsing, event summarization, category filtering,
# report writing). This is a Bedrock cross-region model ID.
CLAUDE_MODEL_ID = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"

# TITAN_EMBED_MODEL_ID: Amazon's embedding model that converts text into
# numerical vectors (lists of 1024 numbers). Used for RAG — we embed
# document chunks and search queries, then compare them by similarity.
TITAN_EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"

"""When Titan Embeddings converts text into a vector, it produces a list of 1024 numbers.     
  That's the "dimension" — how many numbers are in each vector.

  "IAM user creation" → [0.23, 0.87, -0.12, 0.45, ... 1020 more numbers]

  When you create a Pinecone index (which we did through the Pinecone dashboard before       
  writing any code), you have to tell Pinecone: "each vector I'll store will have exactly    
  1024 numbers."

  If there's a mismatch — say Titan produces 1024 numbers but Pinecone expects 768 — Pinecone
   will reject the upload. They must match.

  So the comment is saying: we set EMBEDDING_DIMENSION = 1024 because:
  1. That's what Titan V2 outputs
  2. That's what our Pinecone index was configured to accept
  3. Both sides need to agree on the same number
  """
EMBEDDING_DIMENSION = 1024

# ---------------------------------------------------------------------------
# S3 Bucket Settings
# ---------------------------------------------------------------------------
# CLOUDTRAIL_BUCKET: Where CloudTrail stores its log files automatically.
# CloudTrail was configured to deliver logs to this bucket.
CLOUDTRAIL_BUCKET = f"docugen-cloudtrail-logs-{ACCOUNT_ID}"

# REPORTS_BUCKET: Where we store the generated reports and metadata.
# Our code writes to this bucket after generating each report.
REPORTS_BUCKET = f"docugen-reports-{ACCOUNT_ID}"

# CLOUDTRAIL_PREFIX: The folder path structure inside the CloudTrail bucket.
# CloudTrail organizes files as: AWSLogs/{account}/CloudTrail/{region}/YYYY/MM/DD/
# This prefix gets us to the region level; we append the date folders in code.
CLOUDTRAIL_PREFIX = f"AWSLogs/{ACCOUNT_ID}/CloudTrail/{AWS_REGION}"

# ---------------------------------------------------------------------------
# Pinecone Vector Database Settings
# ---------------------------------------------------------------------------
# PINECONE_API_KEY: Authentication key for Pinecone (loaded from .env).
# This is a secret — never hardcode it or commit it to version control.
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

# PINECONE_INDEX_NAME: The name of our Pinecone index that stores the
# embedded AWS documentation chunks. Created once via Pinecone dashboard.
PINECONE_INDEX_NAME = "docugen-aws-docs"

# ---------------------------------------------------------------------------
# RAG (Retrieval-Augmented Generation) Settings
# ---------------------------------------------------------------------------
# CONFIDENCE_THRESHOLD: Minimum average cosine similarity score required
# for retrieved documents to be considered "sufficient". If the average
# similarity of the top-K results is below this, the system retries with
# a broader query. Set to 0.50 (calibrated for Titan V2's score distribution,
# which tends to produce lower absolute scores than other embedding models).
CONFIDENCE_THRESHOLD = 0.50

# MAX_RETRIES: How many times to retry retrieval with broader queries
# before giving up and generating the report with a low-confidence warning.
# Total attempts = 1 (initial) + MAX_RETRIES = 3.
MAX_RETRIES = 2

# CHUNK_SIZE: How many characters per text chunk when splitting documents
# for indexing. 1000 chars ≈ ~200 words ≈ a focused paragraph. Too small
# and you lose context; too large and similarity search becomes less precise.
CHUNK_SIZE = 1000

# CHUNK_OVERLAP: How many characters overlap between consecutive chunks.
# 200 chars of overlap ensures that if a sentence spans two chunks, it
# appears in both, so nothing is lost at the boundary.
CHUNK_OVERLAP = 200

# TOP_K: How many similar document chunks to retrieve per search query.
# 5 provides enough context without overwhelming the report prompt.
TOP_K = 5

# ---------------------------------------------------------------------------
# Documentation Path
# ---------------------------------------------------------------------------
# DOCS_DIR: Path to the folder containing curated AWS documentation files
# (.md format). These are indexed into Pinecone on first run and used
# for RAG retrieval to ground the generated reports.
DOCS_DIR = os.path.join(os.path.dirname(__file__), "docs", "aws")
