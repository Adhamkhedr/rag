from agents.log_analysis import categorize_event


def test_categorize_iam_events():
    assert categorize_event("CreateUser") == "IAM_CHANGE"
    assert categorize_event("DeleteUser") == "IAM_CHANGE"
    assert categorize_event("AttachUserPolicy") == "IAM_CHANGE"
    assert categorize_event("CreateAccessKey") == "IAM_CHANGE"


def test_categorize_auth_events():
    assert categorize_event("ConsoleLogin") == "AUTH_EVENT"
    assert categorize_event("AssumeRole") == "AUTH_EVENT"


def test_categorize_security_group_events():
    assert categorize_event("AuthorizeSecurityGroupIngress") == "SECURITY_GROUP"
    assert categorize_event("CreateSecurityGroup") == "SECURITY_GROUP"


def test_categorize_s3_events():
    assert categorize_event("CreateBucket") == "S3_CONFIG"
    assert categorize_event("PutBucketPolicy") == "S3_CONFIG"


def test_categorize_ec2_events():
    assert categorize_event("RunInstances") == "EC2_LIFECYCLE"
    assert categorize_event("TerminateInstances") == "EC2_LIFECYCLE"


def test_categorize_cloudtrail_events():
    assert categorize_event("CreateTrail") == "CLOUDTRAIL_CONFIG"
    assert categorize_event("StopLogging") == "CLOUDTRAIL_CONFIG"


def test_categorize_unknown_events():
    assert categorize_event("DescribeInstances") == "OTHER"
    assert categorize_event("SomeFutureEvent") == "OTHER"
