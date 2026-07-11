# 06 - Evidence Templates
This document defines the evidence required for each investigation type.
An Evidence Template specifies **what evidence must be collected** before an assessment can begin.
It does not define execution order.
It does not define implementation details.
---
# Purpose
Evidence Templates standardize infrastructure investigations.
Instead of allowing the Assessment Model to decide what information should be collected, the platform defines deterministic evidence requirements.
This reduces:
- unnecessary iterations
- token usage
- planning errors
- inconsistent investigations
---
# Investigation Flow
```
Intent
↓
Evidence Template
↓
Execution Graph
↓
Evidence
↓
Assessment
```
Evidence Templates describe **what must be collected**, not **how it is collected**.
---
# Evidence Categories
Evidence is organized into reusable categories.
Examples include:
- Hardware
- Operating System
- Services
- Processes
- Packages
- Network
- Storage
- Monitoring
- Security
- Configuration
- Logs
Evidence Templates combine these categories to answer operational questions.
---
# Machine Assessment
Purpose
Evaluate the overall operational health of a machine.
Required Evidence
- System Information
- CPU
- Memory
- Swap
- Storage
- Filesystem
- Network
- Services
Optional Evidence
- Processes
- Time Synchronization
- Recent Logs
- Docker
- Security Status
Expected Outcome
Determine whether the machine is healthy and identify operational risks.
---
# Application Discovery
Purpose
Determine whether an application exists on a target system.
Required Evidence
- Installed Packages
- System Services
- Running Processes
Optional Evidence
- Listening Ports
- Configuration Files
- Containers
Expected Outcome
Determine whether the application exists and how it is deployed.
---
# Service Assessment
Purpose
Evaluate one or more services.
Required Evidence
- Service Status
- Service Configuration
- Service Logs
Optional Evidence
- Running Processes
- Listening Ports
- Dependencies
Expected Outcome
Determine service health and operational status.
---
# Monitoring Assessment
Purpose
Evaluate monitoring platforms.
Required Evidence
- Active Problems
- Triggers
- Alert Severity
- Host Status
Optional Evidence
- Dashboards
- Data Sources
- Event History
Expected Outcome
Summarize current monitoring health and operational impact.
---
# Security Assessment
Purpose
Evaluate security posture.
Required Evidence
- SSH Configuration
- Firewall
- Secure Boot
- AppArmor
- SELinux
Optional Evidence
- Recent Logins
- Listening Ports
- Certificates
Expected Outcome
Identify security risks and hardening opportunities.
---
# Performance Assessment
Purpose
Identify performance bottlenecks.
Required Evidence
- CPU Usage
- Memory Usage
- Disk Usage
- Load Average
Optional Evidence
- Processes
- I/O Statistics
- Network Usage
Expected Outcome
Identify resource bottlenecks affecting performance.
---
# Storage Assessment
Purpose
Evaluate storage health.
Required Evidence
- Filesystems
- Disk Usage
- Mount Points
Optional Evidence
- SMART Status
- RAID Status
- Storage Performance
Expected Outcome
Identify storage capacity or health issues.
---
# Network Assessment
Purpose
Evaluate networking.
Required Evidence
- Network Interfaces
- IP Configuration
- Default Gateway
Optional Evidence
- DNS
- Routing
- Listening Ports
- Firewall
Expected Outcome
Identify connectivity and configuration issues.
---
# Configuration Assessment
Purpose
Review system configuration.
Required Evidence
- Configuration Files
- Installed Packages
- Services
Optional Evidence
- Running Processes
- Environment Variables
Expected Outcome
Determine whether configuration matches expected operational state.
---
# Troubleshooting
Purpose
Investigate operational failures.
Required Evidence
Evidence depends on the reported problem.
The investigation should begin with the smallest evidence set capable of explaining the issue.
Additional evidence should only be collected when required.
Expected Outcome
Identify the most likely root cause while minimizing unnecessary evidence collection.
---
# Required vs Optional Evidence
Every template separates evidence into two categories.
Required Evidence
Must be collected before assessment.
Optional Evidence
Collected only when:
- confidence is insufficient
- additional validation is required
- requested by the user
---
# Reusable Evidence
Evidence categories should be reusable.
Example
```
CPU
```
may be reused by
- Machine Assessment
- Performance Assessment
- Troubleshooting
The platform should never duplicate evidence definitions.
---
# Evidence Completeness
Assessment should begin only after all required evidence has been collected.
Optional evidence should never block an investigation.
---
# Evidence Quality
Evidence should be:
- deterministic
- normalized
- reproducible
- benchmarkable
- independently verifiable
Whenever possible, evidence should represent operational facts instead of raw command output.
---
# Evolution
Evidence Templates should evolve only when benchmark scenarios demonstrate insufficient evidence.
New evidence should not be introduced because it appears generally useful.
---
# Final Principle
Evidence Templates define the minimum information required to answer an operational question.
The platform should improve by refining Evidence Templates rather than increasing AI reasoning.
