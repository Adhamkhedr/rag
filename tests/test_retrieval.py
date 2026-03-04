from agents.retrieval import confidence_check, build_retrieval_query


def test_confidence_sufficient():
    """Should return 'sufficient' when confidence >= threshold."""
    state = {"retrieval_confidence": 0.65, "retry_count": 0}
    assert confidence_check(state) == "sufficient"


def test_confidence_low_with_retries_left():
    """Should return 'retry' when confidence is low and retries remain."""
    state = {"retrieval_confidence": 0.3, "retry_count": 0}
    assert confidence_check(state) == "retry"

    state = {"retrieval_confidence": 0.4, "retry_count": 1}
    assert confidence_check(state) == "retry"


def test_confidence_low_max_retries_reached():
    """Should return 'sufficient' when retries exhausted (proceed with warning)."""
    state = {"retrieval_confidence": 0.3, "retry_count": 2}
    assert confidence_check(state) == "sufficient"


def test_confidence_exact_threshold():
    """Should return 'sufficient' when confidence is exactly at threshold."""
    state = {"retrieval_confidence": 0.50, "retry_count": 0}
    assert confidence_check(state) == "sufficient"


def test_query_broadens_on_retry():
    """Query should get broader with each retry."""
    base_state = {
        "log_findings": {
            "events": [
                {"eventName": "CreateUser", "category": "IAM_CHANGE"},
                {"eventName": "ConsoleLogin", "category": "AUTH_EVENT"},
            ],
            "summary": "test",
        },
    }

    q0 = build_retrieval_query({**base_state, "retry_count": 0})
    q1 = build_retrieval_query({**base_state, "retry_count": 1})
    q2 = build_retrieval_query({**base_state, "retry_count": 2})

    # First query should be category-specific
    assert "IAM" in q0
    # Second query should be broader
    assert "security" in q1.lower()
    # Third query should be the broadest
    assert "incident response" in q2
