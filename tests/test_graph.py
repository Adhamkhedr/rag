import json
from unittest.mock import patch, MagicMock


def test_full_pipeline_integration():
    """Integration test: full pipeline with all external services mocked."""
    time_response = json.dumps({
        "start": "2026-02-03T00:00:00Z",
        "end": "2026-02-03T23:59:59Z",
    })

    summary_response = "1 IAM event: CreateUser by adham."

    filter_response = "IAM_CHANGE"

    report_response = "# Incident Report\n\n## Executive Summary\nTest report."

    call_count = {"n": 0}

    def mock_claude_side_effect(system_prompt, user_message, max_tokens=4096):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return time_response
        elif call_count["n"] == 2:
            return summary_response
        elif call_count["n"] == 3:
            return filter_response
        else:
            return report_response

    mock_cloudtrail_records = [
        {
            "eventTime": "2026-02-03T14:23:00Z",
            "eventName": "CreateUser",
            "userIdentity": {"type": "IAMUser", "userName": "adham"},
            "sourceIPAddress": "203.0.113.50",
            "awsRegion": "us-east-1",
        }
    ]

    mock_pinecone_results = [
        {"content": "IAM users are identities...", "source": "iam-users-guide.md", "similarity": 0.88},
        {"content": "Best practice: use MFA...", "source": "iam-best-practices.md", "similarity": 0.82},
        {"content": "IAM policies control access...", "source": "iam-policies-guide.md", "similarity": 0.80},
        {"content": "Roles delegate permissions...", "source": "iam-roles-guide.md", "similarity": 0.78},
        {"content": "CloudTrail records API calls...", "source": "cloudtrail-overview.md", "similarity": 0.76},
    ]

    with (
        patch("agents.time_parsing.invoke_claude", side_effect=mock_claude_side_effect),
        patch("agents.log_analysis.invoke_claude", side_effect=mock_claude_side_effect),
        patch("agents.report_synthesis.invoke_claude", side_effect=mock_claude_side_effect),
        patch("agents.log_analysis.list_cloudtrail_files", return_value=["fake-key.json.gz"]),
        patch("agents.log_analysis.read_cloudtrail_file", return_value=mock_cloudtrail_records),
        patch("agents.report_synthesis.store_report"),
        patch("agents.retrieval.embed_text", return_value=[0.1] * 1024),
        patch("agents.retrieval.query_vectors", return_value=mock_pinecone_results),
        patch("services.pinecone_client.index_has_data", return_value=True),
    ):
        from graph import run_pipeline

        result = run_pipeline("What IAM changes happened last Tuesday?")

        assert result["final_report"] is not None
        assert "Incident Report" in result["final_report"]
        assert result["metadata"] is not None
        assert result["metadata"]["event_count"] == 1
        assert result["retrieval_confidence"] > 0.75
