# IAM Policies Guide

## Overview

IAM policies are JSON documents that define permissions in AWS. A policy specifies which actions are allowed or denied on which AWS resources and under what conditions. Policies are the primary mechanism for access control in AWS.

## Policy Types

### Identity-Based Policies

Identity-based policies are attached to IAM identities — users, groups, or roles. They grant permissions to the identity they are attached to. There are three subtypes:

- **AWS Managed Policies**: Predefined policies created and maintained by AWS. Examples include `ReadOnlyAccess`, `AdministratorAccess`, and `AmazonS3FullAccess`. These cannot be modified.
- **Customer Managed Policies**: Custom policies created by the account administrator. These can be versioned and attached to multiple identities. You can have up to 5 versions of a customer managed policy.
- **Inline Policies**: Policies embedded directly into a single user, group, or role. They have a strict one-to-one relationship with the identity and are deleted when the identity is deleted.

### Resource-Based Policies

Resource-based policies are attached directly to AWS resources rather than to identities. Common examples include S3 bucket policies, SQS queue policies, and KMS key policies. Resource-based policies include a `Principal` element that specifies which accounts, users, roles, or services are granted access. Resource-based policies enable cross-account access without requiring role assumption in some cases.

### Other Policy Types

- **Permissions Boundaries**: Set the maximum permissions that an identity-based policy can grant. They do not grant permissions on their own.
- **Service Control Policies (SCPs)**: Used in AWS Organizations to set permission guardrails for accounts within an organization.
- **Session Policies**: Passed as parameters when creating a temporary session, further limiting the session's permissions.

## Policy Structure

An IAM policy document is a JSON object with the following structure:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DescriptiveStatementId",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::my-bucket/*",
      "Condition": {
        "StringEquals": {
          "s3:prefix": "home/"
        }
      }
    }
  ]
}
```

### Key Elements

- **Version**: Always use `"2012-10-17"`. This is the current policy language version.
- **Statement**: An array of individual permission statements.
- **Sid** (optional): A statement identifier for documentation purposes.
- **Effect**: Either `"Allow"` or `"Deny"`. There is no default allow; everything is denied unless explicitly allowed.
- **Action**: The specific API actions the statement applies to. Supports wildcards (e.g., `s3:Get*`). Can be a single string or an array.
- **Resource**: The ARN(s) of the resources the statement applies to. Use `"*"` for all resources.
- **Condition** (optional): Conditions under which the statement is in effect, using condition operators like `StringEquals`, `IpAddress`, `DateGreaterThan`, and others.
- **Principal** (resource-based policies only): The account, user, role, or service to which the policy grants access.

## Policy Evaluation Logic

When a principal makes a request, AWS evaluates all applicable policies using the following logic:

1. **Explicit Deny**: If any applicable policy contains an explicit `Deny` for the requested action, the request is denied. Explicit denies always take precedence.
2. **Organizations SCPs**: If the account is part of an AWS Organization, SCPs are evaluated. If the SCP does not allow the action, the request is denied.
3. **Resource-Based Policies**: If a resource-based policy grants access and the requester is in the same account, the request is allowed (even without an identity-based policy granting access).
4. **Permissions Boundaries**: If a permissions boundary is set, the action must be allowed by both the boundary and an identity-based policy.
5. **Identity-Based Policies**: The request is allowed only if at least one identity-based policy grants the requested action.
6. **Default Deny**: If no policy explicitly allows the action, the request is denied.

The critical rule: an explicit `Deny` in any policy always overrides any `Allow`.

## Common Policy Examples

### Allow Read-Only Access to a Specific S3 Bucket

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::example-bucket",
        "arn:aws:s3:::example-bucket/*"
      ]
    }
  ]
}
```

### Deny All Actions Outside a Specific Region

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Deny",
      "Action": "*",
      "Resource": "*",
      "Condition": {
        "StringNotEquals": {
          "aws:RequestedRegion": "us-east-1"
        }
      }
    }
  ]
}
```

### Require MFA for Sensitive Operations

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Deny",
      "Action": ["ec2:StopInstances", "ec2:TerminateInstances"],
      "Resource": "*",
      "Condition": {
        "BoolIfExists": {
          "aws:MultiFactorAuthPresent": "false"
        }
      }
    }
  ]
}
```
