# AWS Security Fundamentals

## Overview

Security in AWS is built on a shared responsibility model and is supported by a comprehensive suite of security services, encryption capabilities, network isolation features, and compliance programs. Understanding these fundamentals is essential for building secure architectures on AWS.

## Shared Responsibility Model

AWS security operates under a shared responsibility model that divides security obligations between AWS and the customer:

### AWS Responsibility ("Security OF the Cloud")

AWS is responsible for the security of the infrastructure that runs all AWS services. This includes:
- Physical security of data centers (environmental controls, access management, surveillance).
- Hardware and software infrastructure (servers, storage, networking equipment).
- Virtualization layer and hypervisor security.
- Network infrastructure (routers, switches, load balancers, firewalls).
- Managed service infrastructure (the underlying platforms for services like RDS, Lambda, S3).

### Customer Responsibility ("Security IN the Cloud")

Customers are responsible for the security of everything they deploy and configure within AWS:
- Identity and access management (IAM users, roles, policies, MFA).
- Data encryption (at rest and in transit).
- Operating system, network, and firewall configuration (for EC2 instances).
- Application-level security (code, dependencies, input validation).
- Client-side data encryption and data integrity.
- Network traffic protection (security groups, NACLs, VPN, TLS).

The division of responsibility varies by service type. For IaaS services like EC2, customers manage the OS and everything above it. For managed services like RDS, AWS manages the OS and database engine patching while customers manage data, access, and encryption. For serverless services like Lambda, AWS manages nearly all infrastructure layers while customers manage code, data, and IAM configuration.

## AWS Security Services

### Amazon GuardDuty

GuardDuty is a threat detection service that continuously monitors for malicious activity and unauthorized behavior. It analyzes AWS CloudTrail management and data events, VPC Flow Logs, and DNS logs. GuardDuty uses machine learning, anomaly detection, and integrated threat intelligence to identify threats such as:
- Compromised EC2 instances communicating with known command-and-control servers.
- Unusual API calls from unfamiliar locations or at unusual times.
- Cryptocurrency mining on EC2 instances.
- S3 bucket compromise (unusual access patterns, data exfiltration indicators).
- Credential exfiltration (access keys used from unexpected IP addresses).

GuardDuty findings are classified by severity (Low, Medium, High) and include detailed context about the affected resource, the threat actor, and recommended remediation.

### AWS Security Hub

Security Hub provides a comprehensive view of security posture across AWS accounts. It aggregates findings from GuardDuty, Inspector, Macie, IAM Access Analyzer, Firewall Manager, and third-party tools into a single dashboard. Security Hub runs automated compliance checks against standards including CIS AWS Foundations Benchmark, AWS Foundational Security Best Practices, PCI DSS, and NIST 800-53. Findings are normalized into the AWS Security Finding Format (ASFF) for consistent processing.

### AWS Config

AWS Config continuously monitors and records your AWS resource configurations. It evaluates configurations against desired settings using Config rules (both AWS managed and custom). When a resource violates a rule, Config flags it as noncompliant. Common Config rules include: `s3-bucket-public-read-prohibited`, `encrypted-volumes`, `iam-root-access-key-check`, `cloudtrail-enabled`, and `restricted-ssh`. Config supports automatic remediation using Systems Manager Automation documents.

### Amazon Inspector

Inspector is a vulnerability management service that automatically discovers EC2 instances, Lambda functions, and container images in Amazon ECR, then scans them for software vulnerabilities and unintended network exposure. Inspector uses the Common Vulnerabilities and Exposures (CVE) database and provides findings with severity ratings and remediation guidance. It continuously scans workloads when new CVEs are published or when instances change.

## Encryption

### Encryption in Transit

All AWS service endpoints support TLS 1.2 (and most support TLS 1.3) for encrypting data in transit. Customers should enforce TLS for their own applications and can use AWS Certificate Manager (ACM) to provision and manage SSL/TLS certificates. VPN connections (Site-to-Site VPN and Client VPN) encrypt traffic between on-premises networks and AWS. Within a VPC, traffic between instances can be encrypted using application-level TLS or VPC encryption features.

### Encryption at Rest

AWS Key Management Service (KMS) is the central service for managing encryption keys. Most AWS services integrate with KMS for encryption at rest, including S3, EBS, RDS, DynamoDB, EFS, and Secrets Manager. KMS keys can be AWS managed (automatically created and rotated) or customer managed (you control the key policy, rotation, and lifecycle). All KMS keys are backed by FIPS 140-2 validated hardware security modules.

For S3, server-side encryption with S3-managed keys (SSE-S3) is enabled by default. EBS volumes can be encrypted at creation using an EBS encryption setting or a KMS key. RDS instances support encryption at rest when specified during database creation.

## VPC Security

A Virtual Private Cloud (VPC) provides network isolation for AWS resources. Key VPC security features:

- **Subnets**: Divide the VPC into public (internet-accessible) and private (no direct internet access) segments.
- **Security Groups**: Stateful firewalls at the instance level. Allow-only rules control inbound and outbound traffic.
- **Network ACLs**: Stateless firewalls at the subnet level. Support both allow and deny rules.
- **VPC Flow Logs**: Capture information about IP traffic going to and from network interfaces. Flow logs can be published to CloudWatch Logs, S3, or Kinesis Data Firehose for analysis and anomaly detection.
- **VPC Endpoints**: Private connections to AWS services without traversing the internet. Gateway endpoints (S3, DynamoDB) and Interface endpoints (powered by AWS PrivateLink) keep traffic within the AWS network.
- **AWS Network Firewall**: A managed firewall service for fine-grained traffic filtering using stateful and stateless rules, domain filtering, and intrusion prevention (IPS).

## Compliance Programs

AWS maintains compliance with a broad set of certifications and frameworks including SOC 1/2/3, ISO 27001/27017/27018, PCI DSS Level 1, HIPAA, FedRAMP, GDPR, and many others. AWS Artifact provides on-demand access to AWS compliance reports and select online agreements. Customers inherit the compliance of the underlying infrastructure but remain responsible for configuring their own workloads to meet specific compliance requirements.
