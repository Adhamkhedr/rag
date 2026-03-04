import pytest
from unittest.mock import patch


@pytest.fixture
def mock_invoke_claude():
    """Mock Claude LLM at the agent level (where it's imported)."""
    with (
        patch("agents.time_parsing.invoke_claude") as mock_tp,
        patch("agents.log_analysis.invoke_claude") as mock_la,
        patch("agents.report_synthesis.invoke_claude") as mock_rs,
    ):
        # Link all mocks so setting return_value on one works for the yielded mock
        class MultiMock:
            def __init__(self):
                self._mocks = [mock_tp, mock_la, mock_rs]
                self.time_parsing = mock_tp
                self.log_analysis = mock_la
                self.event_filter = mock_la  # event_filter uses same import as log_analysis
                self.report_synthesis = mock_rs

            @property
            def return_value(self):
                return self.time_parsing.return_value

            @return_value.setter
            def return_value(self, val):
                for m in self._mocks:
                    m.return_value = val

            @property
            def call_args(self):
                for m in self._mocks:
                    if m.called:
                        return m.call_args
                return None

        yield MultiMock()


@pytest.fixture
def mock_embed_text():
    """Mock Titan Embeddings to return a deterministic 1024-dim vector."""
    with patch("services.bedrock_embeddings.embed_text") as mock:
        mock.return_value = [0.1] * 1024
        yield mock


@pytest.fixture
def mock_s3_client():
    """Mock S3 operations."""
    with patch("services.s3_client.get_client") as mock:
        yield mock


@pytest.fixture
def sample_cloudtrail_events():
    return [
        {
            "eventTime": "2026-02-03T14:23:00Z",
            "eventName": "CreateUser",
            "userIdentity": {"type": "IAMUser", "userName": "adham"},
            "sourceIPAddress": "203.0.113.50",
            "awsRegion": "us-east-1",
        },
        {
            "eventTime": "2026-02-03T15:10:00Z",
            "eventName": "AttachUserPolicy",
            "userIdentity": {"type": "IAMUser", "userName": "adham"},
            "sourceIPAddress": "203.0.113.50",
            "awsRegion": "us-east-1",
        },
        {
            "eventTime": "2026-02-03T16:45:00Z",
            "eventName": "ConsoleLogin",
            "userIdentity": {"type": "Root", "userName": "root"},
            "sourceIPAddress": "198.51.100.10",
            "awsRegion": "us-east-1",
        },
    ]


@pytest.fixture
def sample_state():
    return {
        "query": "What IAM changes happened last Tuesday?",
        "time_range": {
            "start": "2026-02-03T00:00:00Z",
            "end": "2026-02-03T23:59:59Z",
        },
        "log_findings": None,
        "relevant_categories": None,
        "retrieved_docs": None,
        "retrieval_confidence": 0.0,
        "retry_count": 0,
        "final_report": None,
        "metadata": None,
    }


@pytest.fixture
def sample_state_with_findings(sample_state):
    sample_state["log_findings"] = {
        "events": [
            {
                "eventTime": "2026-02-03T14:23:00Z",
                "eventName": "CreateUser",
                "userName": "adham",
                "sourceIP": "203.0.113.50",
                "region": "us-east-1",
                "category": "IAM_CHANGE",
                "targetResource": "new-user",
            },
            {
                "eventTime": "2026-02-03T16:45:00Z",
                "eventName": "ConsoleLogin",
                "userName": "root",
                "sourceIP": "198.51.100.10",
                "region": "us-east-1",
                "category": "AUTH_EVENT",
                "targetResource": "",
            },
        ],
        "summary": "2 events: 1 IAM change (CreateUser) and 1 authentication event (ConsoleLogin by root).",
    }
    return sample_state
