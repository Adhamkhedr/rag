from agents.report_synthesis import report_synthesis_node


def test_report_synthesis_returns_report_and_metadata(
    mock_invoke_claude, sample_state_with_findings
):
    """Report synthesis should return final_report and metadata."""
    mock_invoke_claude.report_synthesis.return_value = "# Incident Report\n\nTest report content."

    state = sample_state_with_findings
    state["retrieved_docs"] = [
        {"content": "IAM users are...", "source": "iam-users-guide.md", "similarity": 0.85}
    ]
    state["retrieval_confidence"] = 0.85

    result = report_synthesis_node(state)

    assert "final_report" in result
    assert "metadata" in result
    assert result["final_report"] == "# Incident Report\n\nTest report content."
    assert result["metadata"]["retrieval_confidence"] == 0.85
    assert "iam-users-guide.md" in result["metadata"]["sources_referenced"]


def test_report_synthesis_includes_low_confidence_warning(
    mock_invoke_claude, sample_state_with_findings
):
    """When confidence is low, the prompt should include a warning."""
    mock_invoke_claude.report_synthesis.return_value = "# Report with disclaimer"

    state = sample_state_with_findings
    state["retrieved_docs"] = []
    state["retrieval_confidence"] = 0.4

    report_synthesis_node(state)

    call_args = mock_invoke_claude.report_synthesis.call_args
    assert call_args is not None
    user_message = call_args[0][1]
    assert "WARNING" in user_message
    assert "BELOW threshold" in user_message
