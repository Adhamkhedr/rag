# IAM Best Practices

## Overview

Following IAM best practices is essential for securing your AWS environment. These recommendations help reduce the risk of unauthorized access, credential compromise, and privilege escalation.

## Lock Away Root User Access Keys

The AWS account root user has unrestricted access to all resources in the account. You should never generate access keys for the root user. If root access keys already exist, you should deactivate and delete them. Instead, use IAM users or roles for day-to-day administrative tasks. The root user should only be used for the small number of tasks that specifically require it, such as changing account-level settings, restoring IAM user permissions, or activating IAM access to the Billing and Cost Management console.

Store the root user credentials in a secure location, such as a hardware security module or a secure vault. Ensure that at least two authorized individuals know how to access the root credentials for emergency purposes.

## Enable Multi-Factor Authentication (MFA)

Enable MFA for all IAM users, especially those with console access or elevated privileges. MFA requires users to provide a second factor of authentication (a time-based one-time password or hardware token response) in addition to their password. This protects accounts even if passwords are compromised.

For the root user, always enable MFA. AWS supports virtual MFA devices (authenticator apps), hardware TOTP tokens, and FIDO2 security keys. FIDO2 keys provide the strongest phishing resistance.

You can enforce MFA usage through IAM policies by denying actions when `aws:MultiFactorAuthPresent` is false. This ensures users cannot perform sensitive operations without completing MFA.

## Grant Least Privilege

Start with minimum permissions and grant additional permissions only as needed. Determine what actions users and roles need to perform, and craft policies that permit only those actions. Avoid using wildcard (`*`) permissions in the Action or Resource elements unless absolutely necessary.

Use AWS IAM Access Analyzer to help identify unused permissions. Access Analyzer can generate policies based on actual access activity recorded in CloudTrail, helping you right-size permissions. Review policies periodically and remove permissions that are no longer needed.

When writing policies, be specific about resources. Instead of granting `s3:*` on all resources, grant only the specific S3 actions needed on the specific buckets required.

## Use Roles for Applications on EC2

Applications running on Amazon EC2 instances should never use long-term access keys embedded in code or configuration files. Instead, use IAM roles attached to EC2 instances through instance profiles. The instance profile provides temporary security credentials that are automatically rotated by the AWS Security Token Service (STS). These credentials are available through the instance metadata service at `http://169.254.169.254/latest/meta-data/iam/security-credentials/<role-name>`.

The AWS SDKs and CLI automatically retrieve and refresh these temporary credentials, so no credential management code is needed. This approach eliminates the risk of access key leakage through source code, logs, or configuration files.

## Use Roles for Cross-Account Access

When you need to grant access to resources across AWS accounts, use IAM roles with cross-account trust policies rather than sharing access keys. The trusting account creates a role with a trust policy that allows the trusted account to assume it. Users in the trusted account then use `sts:AssumeRole` to obtain temporary credentials for the trusting account. This approach provides auditable access and does not require sharing long-term credentials.

## Rotate Credentials Regularly

For IAM users that require access keys, implement a key rotation policy. Each user can have two active access keys, which enables seamless rotation: create a new key, update applications to use the new key, verify the old key is no longer in use, then deactivate and delete the old key.

Use IAM credential reports to identify users with old access keys. You can also use AWS Config rules (such as `access-keys-rotated`) to automatically flag access keys that have not been rotated within a defined period, such as 90 days.

For passwords, configure the account password policy to enforce regular password expiration. Require a minimum password length of at least 14 characters, and require a mix of character types.

## Monitor Activity with CloudTrail and Access Analyzer

Enable AWS CloudTrail in all regions to log all API calls made in your account. CloudTrail records the identity of the caller, the time of the call, the source IP address, the request parameters, and the response. This data is essential for security auditing, incident investigation, and compliance.

Use IAM Access Analyzer to identify resources shared with external entities. Access Analyzer continuously monitors resource-based policies for S3 buckets, IAM roles, KMS keys, Lambda functions, and SQS queues. It generates findings when a policy grants access to a principal outside your zone of trust.

Enable AWS CloudWatch alarms for specific IAM events, such as root user sign-in, console sign-in failures, changes to IAM policies, and unauthorized API calls. Use CloudWatch Logs Insights or Amazon Athena to query CloudTrail logs for detailed investigation.

## Use IAM Groups to Assign Permissions

Instead of attaching policies directly to individual IAM users, create IAM groups that reflect job functions (e.g., Administrators, Developers, Auditors) and attach policies to the groups. Then add users to the appropriate groups. This simplifies permission management and ensures consistency. When a user's role changes, move them to a different group rather than modifying their individual policies.

## Apply Permissions Boundaries

Use permissions boundaries to delegate IAM administration safely. A permissions boundary is a managed policy that sets the maximum permissions an IAM entity can have. Even if an identity-based policy grants broader permissions, the effective permissions are limited to the intersection of the identity-based policy and the permissions boundary. This prevents privilege escalation when delegating user creation to non-administrator IAM users.
