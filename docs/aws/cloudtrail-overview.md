# CloudTrail Overview

## Overview

AWS CloudTrail is a service that provides governance, compliance, operational auditing, and risk auditing of your AWS account. CloudTrail records API calls and related events made in your AWS account and delivers log files to an Amazon S3 bucket. It captures actions taken through the AWS Management Console, AWS SDKs, command line tools, and other AWS services.

## Event Types

CloudTrail records three categories of events:

### Management Events

Management events (also called control plane operations) capture actions performed on resources in your AWS account. These include:

- Creating, modifying, and deleting resources (e.g., `RunInstances`, `CreateBucket`, `PutBucketPolicy`).
- Configuring security (e.g., `AttachRolePolicy`, `CreateUser`, `PutKeyPolicy`).
- Registering devices and configuring logging (e.g., `CreateTrail`, `CreateLogGroup`).
- Console sign-in events.

Management events are recorded by default in all trails and in the Event History. They are available at no additional charge for the last 90 days in Event History.

### Data Events

Data events capture resource-level operations performed on or within a resource. These are high-volume activities such as:

- S3 object-level operations: `GetObject`, `PutObject`, `DeleteObject`.
- Lambda function invocations: `Invoke`.
- DynamoDB table operations: `GetItem`, `PutItem`, `DeleteItem`, `UpdateItem`.
- S3 Access Point operations and S3 Object Lambda operations.

Data events are not recorded by default and must be explicitly configured in a trail. They incur additional charges due to their high volume.

### Insights Events

CloudTrail Insights identifies unusual patterns in management event activity, such as spikes in API call volume or error rates. When Insights detects anomalous activity, it generates an Insights event. This helps identify issues like accidental resource provisioning, hitting service limits, or gaps in periodic maintenance activity.

## Event History

Event History provides a viewable, searchable, downloadable record of the past 90 days of management events in your AWS account. Event History is available in every AWS Region at no additional cost. You can filter events by event name, user name, resource name, event source, and time range. Event History is automatically available without needing to create a trail.

## Trails

A trail is a configuration that enables delivery of CloudTrail events to an S3 bucket, CloudWatch Logs, and Amazon EventBridge. Trails provide a persistent, long-term record of events beyond the 90-day Event History limit.

### Trail Configuration Options

- **Multi-Region Trail**: Records events in all AWS Regions and delivers them to a single S3 bucket. AWS recommends creating at least one multi-region trail.
- **Single-Region Trail**: Records events only in the Region where it is created.
- **Organization Trail**: Records events for all accounts in an AWS Organization. Created from the management account.
- **Log File Validation**: When enabled, CloudTrail creates a digest file every hour that contains a hash of the log files delivered during that period. This allows you to verify that log files have not been modified, deleted, or forged.
- **Encryption**: Log files are encrypted using SSE-S3 by default. You can configure SSE-KMS encryption for additional control and auditing of key usage.

## Log File Delivery

CloudTrail typically delivers log files within 15 minutes of an API call. Log files are written to the S3 bucket in the following path structure:

```
s3://<bucket-name>/AWSLogs/<account-id>/CloudTrail/<region>/YYYY/MM/DD/
```

Each log file contains one or more JSON records. Log files are gzip-compressed. A single log file may contain events from multiple API calls.

## Integration with Other Services

### Amazon CloudWatch Logs

CloudTrail can deliver events to a CloudWatch Logs log group. This enables you to create metric filters and alarms for specific API activities, such as root account usage, security group changes, or IAM policy modifications. Example: create an alarm that triggers when `DeleteBucket` is called.

### Amazon EventBridge

All CloudTrail management events are delivered to EventBridge by default. You can create EventBridge rules that match specific events and trigger automated responses using Lambda functions, SNS notifications, Step Functions, or other targets. This enables real-time response to API activity.

### Amazon Athena

CloudTrail logs stored in S3 can be queried directly using Amazon Athena. AWS provides a predefined table schema for CloudTrail logs. This allows SQL-based analysis of API activity across large time periods without setting up separate infrastructure.

### AWS Security Hub

CloudTrail findings can be surfaced through Security Hub, providing centralized security visibility. Security Hub evaluates whether CloudTrail is properly configured as part of its compliance checks (e.g., CIS AWS Foundations Benchmark).

## CloudTrail Lake

CloudTrail Lake is a managed data lake that lets you aggregate, immutably store, and query CloudTrail events. Unlike trails (which deliver JSON log files to S3), CloudTrail Lake stores events in a purpose-built event data store that supports SQL queries natively. Event data stores can retain data for up to 7 years. CloudTrail Lake supports both AWS events and events from external sources (partner integrations or custom applications).
