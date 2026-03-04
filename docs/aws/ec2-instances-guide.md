# EC2 Instances Guide

## Overview

Amazon Elastic Compute Cloud (Amazon EC2) provides resizable compute capacity in the cloud. EC2 instances are virtual servers that run applications on the AWS infrastructure. You can launch instances from Amazon Machine Images (AMIs), configure networking and security, and manage storage as needed.

## Instance Types

EC2 instance types are grouped into families that are optimized for different workloads:

- **General Purpose (M, T series)**: Balanced compute, memory, and networking. T instances (e.g., `t3.micro`, `t3.medium`) offer burstable CPU performance with a baseline and credits that accumulate during idle periods. M instances (e.g., `m6i.xlarge`, `m7g.large`) provide a consistent balance of resources for diverse workloads.
- **Compute Optimized (C series)**: High-performance processors for compute-intensive tasks such as batch processing, scientific modeling, gaming servers, and machine learning inference. Examples: `c6i.large`, `c7g.xlarge`.
- **Memory Optimized (R, X series)**: Designed for workloads requiring large amounts of RAM, such as in-memory databases, real-time big data analytics, and SAP HANA. Examples: `r6i.2xlarge`, `x2idn.xlarge`.
- **Storage Optimized (I, D series)**: High sequential read/write access to large datasets on local storage. Ideal for data warehousing, distributed file systems, and log processing. Examples: `i3.large`, `d3.xlarge`.
- **Accelerated Computing (P, G, Inf series)**: Hardware accelerators (GPUs, custom chips) for machine learning training, graphics rendering, and inference. Examples: `p4d.24xlarge`, `g5.xlarge`, `inf2.xlarge`.

Instance type naming follows the pattern: `<family><generation><attributes>.<size>`. For example, `m6i.xlarge` is a general-purpose (m), 6th generation, Intel-based (i), extra-large instance.

## Instance Lifecycle

EC2 instances move through the following states:

- **pending**: The instance is being launched. Instance store volumes are erased, and the instance receives its initial metadata.
- **running**: The instance is fully operational. Billing begins (for on-demand instances, billing starts when the instance enters `running`). The instance has a public DNS name (if in a public subnet) and a private IP address.
- **stopping**: The instance is being stopped (only applies to EBS-backed instances). Data on instance store volumes is lost.
- **stopped**: The instance is shut down and not running. No compute charges are incurred (EBS volume charges still apply). The instance retains its instance ID, EBS volumes, and private IP addresses. Public IPv4 addresses are released unless an Elastic IP is associated.
- **shutting-down**: The instance is preparing to be terminated.
- **terminated**: The instance has been permanently deleted. The instance ID remains visible in the console for approximately one hour. EBS volumes may be deleted or preserved based on the `DeleteOnTermination` attribute.

You transition between states using the `RunInstances`, `StopInstances`, `StartInstances`, and `TerminateInstances` API actions.

## Instance Metadata Service (IMDS)

The Instance Metadata Service provides information about a running instance that can be queried from within the instance itself. It is accessible at `http://169.254.169.254/latest/meta-data/`. Key metadata categories include:

- `ami-id`: The AMI used to launch the instance.
- `instance-id`: The unique instance identifier (e.g., `i-0abcd1234efgh5678`).
- `instance-type`: The instance type (e.g., `m6i.xlarge`).
- `local-ipv4`: The private IPv4 address.
- `public-ipv4`: The public IPv4 address (if assigned).
- `iam/security-credentials/<role-name>`: Temporary credentials from the instance's IAM role.
- `placement/availability-zone`: The AZ the instance is in (e.g., `us-east-1a`).

**IMDSv2** is the recommended version. It requires a session token obtained via an HTTP PUT request before metadata can be accessed. This defends against SSRF attacks where an attacker tricks an application into making requests to the metadata endpoint. You can enforce IMDSv2 by setting `HttpTokens` to `required` in the instance metadata options.

## Key Pairs

EC2 uses public-key cryptography for authentication to Linux instances. When launching an instance, you specify a key pair. The public key is placed on the instance, and you use the private key to SSH into it. AWS stores only the public key; the private key is the user's responsibility to store securely. If the private key is lost, you cannot connect to the instance via SSH using that key pair.

For Windows instances, the key pair is used to decrypt the administrator password rather than for direct SSH access.

## User Data

You can pass user data to an instance at launch time. User data scripts run as root on first boot and are commonly used for bootstrapping — installing software, configuring services, or pulling application code. User data is limited to 16 KB (before base64 encoding). It is accessible to anyone on the instance via the metadata service at `http://169.254.169.254/latest/user-data`, so it should not contain secrets.

## Purchasing Options

- **On-Demand**: Pay by the second with no long-term commitment. Suitable for short-term, unpredictable workloads.
- **Reserved Instances**: Commit to 1 or 3 years of usage for up to 72% discount. Available as Standard or Convertible.
- **Spot Instances**: Bid on spare EC2 capacity for up to 90% discount. Instances can be interrupted with a 2-minute warning.
- **Savings Plans**: Flexible pricing model offering savings in exchange for a commitment to a consistent amount of compute usage (measured in $/hour) over 1 or 3 years.
