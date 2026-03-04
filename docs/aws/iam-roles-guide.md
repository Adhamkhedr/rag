# IAM Roles Guide

## Overview

An IAM role is an IAM identity with specific permissions that can be assumed by trusted entities. Unlike an IAM user, a role does not have long-term credentials (password or access keys). Instead, when an entity assumes a role, AWS Security Token Service (STS) provides temporary security credentials consisting of an access key ID, a secret access key, and a session token. These credentials expire after a configurable duration (default 1 hour, maximum 12 hours).

## Role Components

Every IAM role has two key components:

### Trust Policy

The trust policy (also called the role's assume role policy) is a resource-based policy that defines which principals are allowed to assume the role. It specifies trusted entities using the `Principal` element. For example:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:root"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "unique-external-id"
        }
      }
    }
  ]
}
```

The `Principal` can be an AWS account, a specific IAM user or role, an AWS service (e.g., `ec2.amazonaws.com`), or a federated identity provider.

### Permissions Policy

The permissions policy defines what actions the role is allowed to perform once assumed. This is an identity-based policy (managed or inline) attached to the role, identical in structure to policies attached to IAM users or groups.

## Assuming Roles

To assume a role, a principal calls `sts:AssumeRole` (or a variant such as `sts:AssumeRoleWithSAML` or `sts:AssumeRoleWithWebIdentity`). The caller must be authorized by the role's trust policy. Upon successful assumption, STS returns temporary credentials.

The temporary credentials include:
- **AccessKeyId**: Begins with `ASIA` (as opposed to `AKIA` for long-term keys).
- **SecretAccessKey**: Used to sign requests.
- **SessionToken**: Must be included with every request made using the temporary credentials.
- **Expiration**: The UTC timestamp at which the credentials expire.

Applications using AWS SDKs handle credential refresh automatically when configured with a role.

## Cross-Account Access

IAM roles are the primary mechanism for granting cross-account access. The pattern involves:

1. **Account A** (trusting account) creates a role with a trust policy that allows Account B to assume it.
2. **Account B** (trusted account) grants its users or roles permission to call `sts:AssumeRole` on Account A's role.
3. A principal in Account B calls `sts:AssumeRole` with the ARN of the role in Account A.
4. The principal receives temporary credentials scoped to Account A with the role's permissions.

For third-party cross-account access, use an External ID in the trust policy's condition to prevent the confused deputy problem. The external ID is a shared secret between the trusting account and the third party.

## Service Roles

A service role is an IAM role that an AWS service assumes to perform actions on your behalf. For example, you create a role that Amazon EC2 can assume to access S3 buckets. The trust policy for a service role specifies the service as the principal:

```json
{
  "Principal": {
    "Service": "ec2.amazonaws.com"
  }
}
```

Common service roles include roles for EC2, Lambda, ECS tasks, and CodeBuild.

## Service-Linked Roles

A service-linked role is a unique type of service role that is linked directly to an AWS service. Service-linked roles are predefined by the service and include all the permissions the service requires. You cannot modify the permissions of a service-linked role. Examples include `AWSServiceRoleForElasticLoadBalancing` and `AWSServiceRoleForAutoScaling`.

Service-linked roles are created automatically when you use certain features, or you can create them manually using IAM. They follow the naming convention `AWSServiceRoleFor<ServiceName>`. These roles can only be deleted after ensuring the linked service no longer requires them.

## Instance Profiles

An instance profile is a container for an IAM role that you can use to pass role information to an EC2 instance at launch. When you create a role for EC2 using the AWS Management Console, an instance profile with the same name is automatically created. When using the CLI or API, you must create the instance profile separately and add the role to it.

An EC2 instance can have only one instance profile, and each instance profile can contain only one role. The instance obtains temporary credentials through the Instance Metadata Service (IMDS) at the endpoint `http://169.254.169.254/latest/meta-data/iam/security-credentials/<role-name>`.

AWS recommends using IMDSv2 (Instance Metadata Service Version 2), which requires session-oriented requests using a PUT request to obtain a token before querying metadata. This mitigates SSRF attack vectors.

## Role Chaining

Role chaining occurs when a role assumes another role. For example, Role A in Account 1 assumes Role B in Account 2, and then Role B assumes Role C in Account 3. Each assumption returns new temporary credentials. When using role chaining, the maximum session duration is limited to 1 hour regardless of the role's configured maximum.

## Role Session Names and Tags

When assuming a role, the caller specifies a `RoleSessionName` that appears in CloudTrail logs, enabling you to identify who performed actions under the role. Session tags can also be passed during role assumption, providing additional attributes that can be used in policy conditions for attribute-based access control (ABAC).
