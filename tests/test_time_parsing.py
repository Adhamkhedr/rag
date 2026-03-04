import json
from agents.time_parsing import time_parsing_node


def test_time_parsing_returns_time_range(mock_invoke_claude):
    """Time parsing agent should return a valid time range dict."""
    mock_invoke_claude.time_parsing.return_value = json.dumps({
        "start": "2026-02-03T00:00:00Z",
        "end": "2026-02-03T23:59:59Z",
    })

    state = {"query": "What happened last Tuesday?"}
    result = time_parsing_node(state)

    assert "time_range" in result
    assert "start" in result["time_range"]
    assert "end" in result["time_range"]
    assert result["time_range"]["start"] == "2026-02-03T00:00:00Z"


def test_time_parsing_strips_markdown_fences(mock_invoke_claude):
    """Time parsing should handle Claude wrapping JSON in markdown code fences."""
    mock_invoke_claude.time_parsing.return_value = (
        '```json\n{"start": "2026-02-06T00:00:00Z", "end": "2026-02-06T23:59:59Z"}\n```'
    )

    state = {"query": "What happened yesterday?"}
    result = time_parsing_node(state)

    assert result["time_range"]["start"] == "2026-02-06T00:00:00Z"
    assert result["time_range"]["end"] == "2026-02-06T23:59:59Z"


def test_time_parsing_calls_claude_with_query(mock_invoke_claude):
    """Time parsing should pass the user's query to Claude."""
    mock_invoke_claude.time_parsing.return_value = json.dumps({
        "start": "2026-02-07T00:00:00Z",
        "end": "2026-02-07T23:59:59Z",
    })

    state = {"query": "Show me IAM changes from today"}
    time_parsing_node(state)

    call_args = mock_invoke_claude.time_parsing.call_args
    assert call_args is not None
    # user_message is the second positional arg
    assert "Show me IAM changes from today" in call_args[0][1]
