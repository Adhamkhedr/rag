# Lambda Overview

## Overview

AWS Lambda is a serverless compute service that runs code in response to events and automatically manages the underlying compute resources. With Lambda, you upload your code as a function, and Lambda handles provisioning, scaling, and managing the infrastructure needed to execute it. Lambda supports multiple runtimes including Python, Node.js, Java, Go, .NET, Ruby, and custom runtimes via Lambda layers.

## Function Configuration

A Lambda function consists of:

- **Function code**: The application logic, packaged as a deployment package (ZIP file up to 50 MB compressed / 250 MB uncompressed) or a container image (up to 10 GB).
- **Runtime**: The language runtime (e.g., `python3.12`, `nodejs20.x`, `java21`).
- **Handler**: The method in your code that Lambda calls to begin execution (e.g., `index.handler` for a Node.js function where `index` is the file name and `handler` is the exported function).
- **Memory**: Configurable from 128 MB to 10,240 MB (10 GB) in 1 MB increments. CPU power scales proportionally with memory — a function with 1,769 MB has the equivalent of one full vCPU.
- **Timeout**: Maximum execution time, from 1 second to 15 minutes (900 seconds).
- **Environment variables**: Key-value pairs available to the function at runtime. Can be encrypted with KMS.
- **Ephemeral storage**: The `/tmp` directory provides 512 MB to 10,240 MB of temporary storage.

## Execution Model

When a Lambda function is invoked, Lambda creates an execution environment (or reuses an existing one) to process the request. The execution environment lifecycle is:

1. **INIT phase**: Lambda downloads the code, initializes the runtime, and runs the function's initialization code (code outside the handler). This phase has a timeout of 10 seconds.
2. **INVOKE phase**: Lambda runs the handler function with the event payload. This is subject to the configured timeout.
3. **SHUTDOWN phase**: After the invocation completes, the execution environment may be frozen and reused for subsequent invocations. If no invocation occurs within a certain period (typically minutes), the environment is destroyed.

### Cold Starts

A cold start occurs when Lambda must create a new execution environment, which includes downloading code, starting the runtime, and running initialization code. Cold starts add latency (typically 100ms to several seconds depending on runtime, code size, and VPC configuration). Warm invocations reuse existing environments and skip the INIT phase.

To mitigate cold starts, you can use **Provisioned Concurrency**, which keeps a specified number of execution environments initialized and ready to respond. Provisioned concurrency incurs charges even when functions are not executing.

## Event Sources

Lambda functions are invoked in response to events. There are three invocation patterns:

### Synchronous Invocation

The caller waits for the function to complete and receives the response. Examples: API Gateway, Application Load Balancer, CloudFront (Lambda@Edge), SDK direct invoke. If the function fails, the caller is responsible for retrying.

### Asynchronous Invocation

The caller sends the event and Lambda queues it for processing. Lambda automatically retries failed invocations twice (configurable). Failed events can be sent to a dead-letter queue (SQS or SNS) or a Lambda destination. Examples: S3 event notifications, SNS, EventBridge, CloudWatch Events.

### Event Source Mappings

Lambda polls the event source and invokes the function with batches of records. Examples: SQS queues, DynamoDB Streams, Kinesis Data Streams, Amazon MSK, self-managed Apache Kafka. Lambda manages the polling and batch size. For stream-based sources, Lambda reads records sequentially from each shard.

## Permissions

### Execution Role

Every Lambda function has an execution role — an IAM role that Lambda assumes when running the function. The execution role grants the function permissions to access AWS services and resources. For example, a function that reads from S3 and writes to DynamoDB needs an execution role with `s3:GetObject` and `dynamodb:PutItem` permissions.

The execution role's trust policy must allow `lambda.amazonaws.com` to assume the role. AWS provides managed policies such as `AWSLambdaBasicExecutionRole` (CloudWatch Logs permissions) and `AWSLambdaVPCAccessExecutionRole` (VPC networking permissions).

### Resource-Based Policies

Resource-based policies on a Lambda function specify which principals can invoke or manage the function. These are used to grant other AWS services, accounts, or organizations permission to invoke the function. For example, allowing S3 to invoke the function when an object is created:

```json
{
  "Effect": "Allow",
  "Principal": {
    "Service": "s3.amazonaws.com"
  },
  "Action": "lambda:InvokeFunction",
  "Resource": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
  "Condition": {
    "ArnLike": {
      "AWS:SourceArn": "arn:aws:s3:::my-bucket"
    }
  }
}
```

## Concurrency

Concurrency is the number of function instances processing events simultaneously. Each account has a default regional concurrency limit of 1,000 (can be increased). Concurrency types:

- **Unreserved concurrency**: Shared across all functions in the account. If one function consumes all concurrency, other functions may be throttled.
- **Reserved concurrency**: A function-specific limit that guarantees a portion of the account's concurrency and caps the function's maximum concurrency.
- **Provisioned concurrency**: Pre-initialized execution environments that eliminate cold starts. Useful for latency-sensitive workloads.

When the concurrency limit is reached, additional invocations are throttled (synchronous invocations receive a 429 error; asynchronous invocations are queued and retried).

## VPC Configuration

Lambda functions can be configured to access resources inside a VPC. When VPC-enabled, Lambda creates Elastic Network Interfaces (ENIs) in the specified subnets. The function's outbound traffic routes through the VPC. A VPC-connected function needs a NAT Gateway or VPC endpoints to access the internet or other AWS services outside the VPC.
