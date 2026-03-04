# EC2 Security Groups

## Overview

A security group acts as a virtual firewall for Amazon EC2 instances, controlling inbound and outbound traffic at the instance level. Security groups are associated with network interfaces. When you launch an instance in a VPC, you can assign it up to five security groups. If you do not specify a security group, the instance is assigned the VPC's default security group.

## Inbound and Outbound Rules

Security group rules control the traffic that is allowed to reach and leave the resources associated with the security group.

### Inbound Rules

Inbound rules control incoming traffic to the instance. Each rule specifies:
- **Protocol**: TCP, UDP, ICMP, or a protocol number. Use `-1` or `All` for all protocols.
- **Port Range**: The port or range of ports to allow (e.g., 22 for SSH, 443 for HTTPS, 0-65535 for all ports).
- **Source**: The origin of the traffic. This can be a CIDR block (e.g., `10.0.0.0/16`, `0.0.0.0/0`), another security group ID, or a prefix list. Using another security group as the source allows all instances associated with that group to communicate on the specified port.

### Outbound Rules

Outbound rules control traffic leaving the instance. The structure is similar to inbound rules, but specifies a **Destination** instead of a Source. By default, security groups allow all outbound traffic. You can restrict outbound traffic by removing the default rule and adding specific outbound rules.

## Stateful Behavior

Security groups are stateful. This means:

- If you allow an inbound request from a specific IP on port 443, the response traffic for that request is automatically allowed regardless of outbound rules.
- If an instance initiates an outbound connection (allowed by outbound rules), the response traffic is automatically allowed regardless of inbound rules.
- Connection tracking is used to manage this state. Tracked connections persist even if you modify security group rules. Untracked connections (such as traffic allowed by a rule with source `0.0.0.0/0`) are immediately affected by rule changes.

This stateful behavior is a key distinction from Network ACLs, which are stateless.

## Default Security Group

Every VPC has a default security group. Its initial rules are:

- **Inbound**: Allows all traffic from other instances assigned to the same default security group (source is the security group itself).
- **Outbound**: Allows all traffic to all destinations (`0.0.0.0/0` and `::/0`).

You can modify the rules of the default security group, but you cannot delete the default security group itself. If you do not want instances to use the default security group, create custom security groups and specify them at launch.

## Security Groups vs Network ACLs (NACLs)

Security groups and NACLs both control network traffic, but they differ in several important ways:

| Feature | Security Group | Network ACL |
|---|---|---|
| Scope | Instance level (network interface) | Subnet level |
| State | Stateful (return traffic automatically allowed) | Stateless (return traffic must be explicitly allowed) |
| Rule Type | Allow rules only | Allow and Deny rules |
| Rule Evaluation | All rules evaluated before deciding | Rules evaluated in order by number; first match wins |
| Default Behavior | Denies all inbound, allows all outbound | Default NACL allows all; custom NACL denies all |
| Association | Applied to instances explicitly | Applied to all instances in the subnet automatically |

A common security architecture uses NACLs as a coarse-grained subnet-level filter and security groups as fine-grained instance-level controls.

## Security Group Referencing

Security groups can reference other security groups in their rules, which is a powerful feature for multi-tier architectures. For example:

- A web tier security group allows inbound traffic on port 443 from `0.0.0.0/0`.
- An application tier security group allows inbound traffic on port 8080 only from the web tier security group.
- A database tier security group allows inbound traffic on port 3306 only from the application tier security group.

This pattern ensures that only authorized tiers can communicate with each other, regardless of individual IP addresses.

## Limits and Considerations

- You can assign up to 5 security groups per network interface (adjustable up to 16).
- Each security group can have up to 60 inbound rules and 60 outbound rules (adjustable).
- Security groups are VPC-specific; they cannot span VPCs.
- Changes to security group rules take effect immediately — no restart or reboot is required.
- Security groups cannot block traffic to or from the Amazon DNS server, the instance metadata service (169.254.169.254), or the Amazon Time Sync Service. To control metadata access, use instance metadata options (IMDSv2 enforcement) rather than security groups.
- When troubleshooting connectivity, check both the security group rules and the NACL rules for the relevant subnet.
