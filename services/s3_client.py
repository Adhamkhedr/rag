"""
S3 Client Service — CloudTrail Log Reading + Report Storage
=============================================================
This service handles all communication with Amazon S3. It does two things:

1. READ CloudTrail logs: Download and decompress log files from the
   CloudTrail bucket for a given time range.

2. WRITE reports: Save generated reports and metadata to the reports bucket.

How CloudTrail logs are organized in S3:
    CloudTrail automatically saves log files to S3 in this structure:
        AWSLogs/{account_id}/CloudTrail/{region}/YYYY/MM/DD/
            {account_id}_CloudTrail_{region}_{timestamp}_{random}.json.gz

    Example real path:
        AWSLogs/523761210523/CloudTrail/us-east-1/2026/02/08/
            523761210523_CloudTrail_us-east-1_20260208T1100Z_abc123.json.gz

    Each .json.gz file is a compressed JSON containing a batch of events
    (not one event per file). CloudTrail delivers batches every ~5-15 minutes.

Why two levels of time filtering:
    Level 1 (file-level): The filename contains a timestamp (e.g., T1100Z).
        We skip downloading files outside the requested time range entirely.
        This saves bandwidth — no point downloading a file from 3 AM if the
        user asked about events between 2 PM and 4 PM.

    Level 2 (event-level): Done in log_analysis.py, not here.
        Even after file-level filtering, individual events inside a file
        may fall slightly outside the requested range (batch boundaries
        aren't perfectly clean). The log analysis agent checks each event's
        individual timestamp.

How reports are stored:
    Generated reports are saved as two files in the reports bucket:
        reports/2026-02-08/{report_id}-report.md      — the Markdown report
        reports/2026-02-08/{report_id}-metadata.json   — query, confidence, sources

Singleton pattern:
    Same as the Bedrock services — one shared S3 client for all operations.
"""

import boto3       # AWS SDK for Python — lets us interact with AWS services
import gzip        # For decompressing .gz files (CloudTrail logs are compressed)
import json        # For parsing JSON data inside the log files
import re          # For regex — used to extract timestamps from file names
from datetime import datetime, timedelta
from config import AWS_REGION, CLOUDTRAIL_BUCKET, CLOUDTRAIL_PREFIX, REPORTS_BUCKET

# ---------------------------------------------------------------------------
# Singleton S3 client — created once and reused for all S3 operations.
# This avoids creating a new connection to AWS every time we need to
# read a log file or write a report.
# ---------------------------------------------------------------------------
_client = None


def get_client():
    """Return the shared S3 client, creating it on first call.

    boto3.client("s3") creates a connection to the S3 service.
    region_name tells AWS which data center to connect to.
    """
    global _client
    if _client is None:
        _client = boto3.client("s3", region_name=AWS_REGION)
    return _client


def list_cloudtrail_files(start: datetime, end: datetime) -> list[str]:
    """Find all CloudTrail log files in S3 that fall within the given time range.

    This is the file-level filter (Level 1). It:
    1. Loops through each day in the range (e.g., Feb 6, Feb 7, Feb 8)
    2. Builds the S3 folder path for that day
    3. Lists all .json.gz files in that folder
    4. Extracts the timestamp from each filename using regex
    5. Only keeps files whose timestamp falls within the requested range

    Args:
        start: Start of the time range (timezone-aware datetime from Step 1)
        end:   End of the time range (timezone-aware datetime from Step 1)

    Returns:
        List of S3 object keys (file paths within the bucket) to download.
        Example: ["AWSLogs/.../20260208T1100Z_abc.json.gz", ...]
    """
    client = get_client()
    matching_keys = []

    # Convert datetimes to dates so we can loop day by day.
    # For a range like "Feb 6 14:00 to Feb 8 10:00", we need to check
    # the folders for Feb 6, Feb 7, AND Feb 8.
    current_date = start.date()
    end_date = end.date()

    # Loop through each day in the time range
    while current_date <= end_date:
        # Build the S3 prefix (folder path) for this specific day.
        # Example: "AWSLogs/523761210523/CloudTrail/us-east-1/2026/02/08/"
        # S3 doesn't have real folders — the prefix just filters which
        # file paths (keys) are returned. Any key that STARTS with this
        # prefix will be included in the listing.
        prefix = (
            f"{CLOUDTRAIL_PREFIX}/"
            f"{current_date.year:04d}/{current_date.month:02d}/{current_date.day:02d}/"
        )

        # A paginator handles the case where there are many files.
        # S3's list_objects_v2 returns max 1000 files per request.
        # The paginator automatically makes multiple requests if needed
        # and yields results page by page.
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=CLOUDTRAIL_BUCKET, Prefix=prefix):
            # Each page contains a "Contents" list of file objects.
            # If the folder is empty, "Contents" won't exist — hence .get()
            for obj in page.get("Contents", []):
                # "Key" is the full file path in S3.
                # Example: "AWSLogs/.../20260208T1100Z_abc123.json.gz"
                key = obj["Key"]

                # Skip any files that aren't compressed JSON logs.
                # The folder might contain digest files or other metadata.
                if not key.endswith(".json.gz"):
                    continue

                # Extract the timestamp from the filename using regex.
                # Pattern: 8 digits + T + 4 digits + Z
                # Example: "20260208T1100Z" from the filename
                # This tells us roughly when the events in this file
                # were recorded by CloudTrail.
                match = re.search(r"(\d{8}T\d{4})Z", key)
                if not match:
                    continue

                # Parse the extracted timestamp string into a datetime.
                # "20260208T1100" → datetime(2026, 2, 8, 11, 0)
                file_time_str = match.group(1)
                file_time = datetime.strptime(file_time_str, "%Y%m%dT%H%M")
                # Copy the timezone info from the start parameter so
                # comparison works (can't compare aware vs naive datetimes).
                file_time = file_time.replace(tzinfo=start.tzinfo)

                # Only keep this file if its timestamp falls within our range.
                # This prevents downloading files we don't need.
                if start <= file_time <= end:
                    matching_keys.append(key)

        # Move to the next day
        current_date += timedelta(days=1)

    return matching_keys


def read_cloudtrail_file(key: str) -> list[dict]:
    """Download a single CloudTrail log file from S3, decompress it, and return events.

    Each CloudTrail log file is a gzip-compressed JSON file containing:
    {
        "Records": [
            {"eventTime": "...", "eventName": "CreateUser", "userIdentity": {...}, ...},
            {"eventTime": "...", "eventName": "GetBucketAcl", "userIdentity": {...}, ...},
            ...
        ]
    }

    Each record has 50+ fields. We return the full raw records — the log
    analysis agent (Step 2) picks which fields to keep.

    Args:
        key: The S3 object key (file path) to download.
             Example: "AWSLogs/.../20260208T1100Z_abc123.json.gz"

    Returns:
        List of raw CloudTrail event dictionaries from the "Records" array.
    """
    client = get_client()

    # Download the file from S3.
    # get_object returns the file content in response["Body"] as a
    # streaming object (not loaded entirely into memory until .read()).
    response = client.get_object(Bucket=CLOUDTRAIL_BUCKET, Key=key)

    # Read the raw compressed bytes from the stream.
    compressed = response["Body"].read()

    # Decompress from gzip format back to plain JSON text.
    # CloudTrail uses gzip compression to save storage space.
    # A typical file: ~5KB compressed → ~50KB decompressed.
    decompressed = gzip.decompress(compressed)

    # Parse the JSON text into a Python dictionary.
    data = json.loads(decompressed)

    # Return just the events list. If "Records" key is somehow missing
    # (shouldn't happen with valid CloudTrail files), return empty list.
    return data.get("Records", [])


def store_report(report_id: str, report_md: str, metadata: dict):
    """Save a generated report and its metadata to the reports S3 bucket.

    Creates two files in S3, organized by date:
        reports/2026-02-08/{report_id}-report.md      — the Markdown report
        reports/2026-02-08/{report_id}-metadata.json   — query details, confidence, etc.

    This provides a persistent, auditable record of every generated report.
    The metadata file makes it easy to search/filter reports later.

    Args:
        report_id:  Unique identifier for this report (UUID generated by
                    the report synthesis agent).
        report_md:  The full Markdown report text.
        metadata:   Dictionary containing query, confidence score, sources
                    referenced, model used, timestamp, etc.
    """
    client = get_client()

    # Use today's date to organize reports into daily folders.
    date_str = datetime.utcnow().strftime("%Y-%m-%d")

    # Upload the Markdown report.
    # put_object creates (or overwrites) a file in S3.
    client.put_object(
        Bucket=REPORTS_BUCKET,                              # Which bucket to save in
        Key=f"reports/{date_str}/{report_id}-report.md",    # The file path/name in S3
        Body=report_md.encode("utf-8"),                     # The file content (as bytes)
        ContentType="text/markdown",                        # Tells S3 this is a Markdown file
    )

    # Upload the metadata JSON (query details, confidence score, sources, etc.).
    # indent=2 makes the JSON human-readable if opened directly.
    client.put_object(
        Bucket=REPORTS_BUCKET,
        Key=f"reports/{date_str}/{report_id}-metadata.json",
        Body=json.dumps(metadata, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
