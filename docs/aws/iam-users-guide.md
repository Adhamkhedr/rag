# IAM Users Guide

## Overview

An IAM user is an entity that you create in AWS to represent the person or application that interacts with AWS services and resources. An IAM user consists of a name and credentials. Each IAM user is associated with one and only one AWS account.

## The Root User vs IAM Users

When you first create an AWS account, you begin with a single sign-in identity known as the root user. The root user is accessed by signing in with the email address and password used to create the account. The root user has complete, unrestricted access to all resources in the AWS account, including billing information and the ability to change the account password.

IAM users, by contrast, are identities created within the IAM service. Each IAM user has its own credentials and permissions. Unlike the root user, IAM user permissions are governed entirely by IAM policies. By default, a newly created IAM user has no permissions whatsoever — access must be explicitly granted.

AWS strongly recommends that you do not use the root user for everyday tasks. Instead, create individual IAM users for each person who needs access to your AWS account.

## Types of IAM User Credentials

### Console Password

An IAM user can be assigned a password that allows them to sign in to the AWS Management Console. Passwords must conform to the account's password policy, which administrators can configure to enforce minimum length, character requirements, expiration, and reuse prevention. Console passwords are used only for interactive sign-in through a web browser.

### Access Keys

Access keys are long-term credentials used for programmatic access to AWS. Each access key consists of two parts: an access key ID (e.g., `AKIAIOSFODNN7EXAMPLE`) and a secret access key (e.g., `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY`). The secret access key is shown only once at creation time and cannot be retrieved later. If lost, the access key must be deleted and a new one created.

Each IAM user can have a maximum of two access keys at any time. This allows for key rotation: you create a second key, update all applications to use the new key, and then deactivate and delete the old key.

### Multi-Factor Authentication (MFA)

MFA adds an extra layer of security by requiring a second form of authentication in addition to a password. AWS supports virtual MFA devices (such as Google Authenticator or Authy), hardware TOTP tokens, and FIDO2 security keys. MFA can be enabled for both console sign-in and API operations using `sts:GetSessionToken` or role assumption.

## IAM User ARNs

Every IAM user has a unique Amazon Resource Name (ARN) that identifies the user across all of AWS. The ARN format for an IAM user is:

```
arn:aws:iam::<account-id>:user/<user-name>
```

For users created within a path (used for organizational grouping), the ARN includes the path:

```
arn:aws:iam::<account-id>:user/<path>/<user-name>
```

For example: `arn:aws:iam::123456789012:user/developers/jane`. The path has no effect on permissions; it is purely an organizational tool. User ARNs are used in IAM policies to grant or restrict access to specific users.

## User Limits and Characteristics

- An AWS account can have up to 5,000 IAM users.
- Each IAM user can be a member of up to 10 IAM groups.
- Each IAM user can have up to 2 access keys.
- IAM user names can be up to 64 characters long and must be unique within the account.
- IAM user names are case-insensitive for sign-in purposes but are stored with the original case.

## Federated Users vs IAM Users

For organizations with existing identity systems, AWS supports identity federation as an alternative to creating individual IAM users. Federated users authenticate through an external identity provider (IdP) such as Active Directory, Okta, or any SAML 2.0-compatible provider. Federated users assume IAM roles and receive temporary security credentials. This approach is recommended for large organizations because it centralizes identity management and avoids the need to create and maintain individual IAM users.

## Programmatic and Console Access

When creating an IAM user, you choose what type of access the user needs. A user can have console access only (password), programmatic access only (access keys), or both. Users with only programmatic access cannot sign in to the AWS Management Console. Users with only console access cannot make API calls using access keys. The type of access can be modified at any time after user creation.
