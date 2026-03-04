# S3 Buckets Guide

## Overview

Amazon Simple Storage Service (Amazon S3) is an object storage service that provides industry-leading scalability, data availability, security, and performance. S3 stores data as objects within buckets. An object consists of a file and optional metadata, and is identified by a unique key within the bucket.

## Core Concepts

### Buckets

A bucket is a container for objects stored in S3. Every object is contained in a bucket. Bucket names are globally unique across all AWS accounts and must comply with DNS naming conventions: 3-63 characters, lowercase letters, numbers, and hyphens only, must start with a letter or number. Buckets are created in a specific AWS Region, and data does not leave that Region unless explicitly transferred.

### Objects

An object consists of:
- **Key**: The unique identifier for the object within the bucket (e.g., `logs/2024/01/access.log`).
- **Value**: The actual data (file content), up to 5 TB per object.
- **Metadata**: A set of name-value pairs. System metadata includes Content-Type, Content-Length, and Last-Modified. User-defined metadata keys must begin with `x-amz-meta-`.
- **Version ID**: If versioning is enabled, each object version has a unique version ID.

### Keys and Prefixes

S3 has a flat namespace — there are no actual directories. However, the key naming convention using forward slashes (e.g., `photos/2024/january/sunset.jpg`) creates a logical hierarchy. The Console displays these as folders. The portion of the key before the last slash is called the prefix, and S3 APIs support prefix-based listing and filtering.

## Storage Classes

S3 offers multiple storage classes optimized for different access patterns and cost requirements:

- **S3 Standard**: High durability (99.999999999%), high availability (99.99%). Default storage class for frequently accessed data.
- **S3 Intelligent-Tiering**: Automatically moves objects between frequent and infrequent access tiers based on usage patterns. No retrieval fees.
- **S3 Standard-IA (Infrequent Access)**: Lower storage cost than Standard, with a per-GB retrieval fee. Minimum storage duration of 30 days. Suitable for data accessed less than once per month.
- **S3 One Zone-IA**: Same as Standard-IA but stored in a single Availability Zone. Lower cost, lower resilience.
- **S3 Glacier Instant Retrieval**: Archive storage with millisecond retrieval. Minimum 90-day storage duration.
- **S3 Glacier Flexible Retrieval**: Archive storage with retrieval times from minutes to hours. Minimum 90-day storage.
- **S3 Glacier Deep Archive**: Lowest cost storage. Retrieval time of 12-48 hours. Minimum 180-day storage. Designed for data retained for 7-10 years or longer.

## Versioning

Bucket versioning preserves every version of every object in the bucket. When versioning is enabled:

- Uploading an object with the same key creates a new version rather than overwriting the existing object.
- Deleting an object inserts a delete marker rather than permanently removing the object. The previous versions remain accessible by specifying the version ID.
- Versioning can be suspended but not disabled once enabled. Suspending versioning stops creating new versions but does not delete existing versions.

Versioning is essential for data protection and is a prerequisite for S3 Cross-Region Replication and S3 Object Lock.

## Lifecycle Policies

S3 lifecycle policies automate the transition of objects between storage classes and the expiration (deletion) of objects. A lifecycle configuration is a set of rules that define actions:

- **Transition actions**: Move objects to a different storage class after a specified number of days. For example, move objects to Standard-IA after 30 days and to Glacier after 90 days.
- **Expiration actions**: Permanently delete objects after a specified number of days. For versioned buckets, you can specify rules to delete noncurrent versions after a certain number of days.

Lifecycle rules can apply to the entire bucket, a specific prefix, or objects with specific tags. Common patterns include transitioning logs to cheaper storage after 30 days and deleting them after 365 days.

## Encryption at Rest

S3 provides multiple options for encrypting objects at rest:

- **SSE-S3 (Server-Side Encryption with S3-Managed Keys)**: S3 manages the encryption keys. Each object is encrypted with a unique key, which is itself encrypted by a root key that S3 rotates regularly. This is enabled by default for all new buckets as of January 2023.
- **SSE-KMS (Server-Side Encryption with AWS KMS Keys)**: Uses AWS Key Management Service to manage encryption keys. Provides an audit trail of key usage via CloudTrail and allows you to control key policies. You can use the AWS managed key (`aws/s3`) or a customer managed key.
- **SSE-C (Server-Side Encryption with Customer-Provided Keys)**: You provide the encryption key with every request. S3 performs the encryption/decryption but does not store the key. You are responsible for managing the keys.
- **Client-Side Encryption**: You encrypt the data before uploading it to S3. S3 stores the ciphertext and has no knowledge of the encryption.

## Data Consistency

S3 provides strong read-after-write consistency for all operations. After a successful PUT or DELETE, any subsequent read request immediately returns the latest version of the object. This applies to reads of objects, list operations, and metadata retrieval.
