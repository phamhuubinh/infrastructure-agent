# 05 - Intent Library
This document defines the standard investigation intents supported by the platform.
An Intent represents **what the user wants to know**, not **how the system will answer it**.
Intent Resolution should be deterministic whenever possible.
---
# Purpose
The Intent Library provides a consistent mapping between user requests and investigation objectives.
Every investigation begins by identifying exactly one primary intent.
Additional intents may be identified only when required.
---
# Intent Flow
```
User Request
↓
Intent
↓
Target
↓
Evidence Template
↓
Execution Graph
↓
Evidence
↓
Assessment
```
The Intent Library never performs execution.
It only identifies the investigation objective.
---
# Intent Categories
The platform currently supports the following investigation categories.
## Machine Assessment
Purpose
Evaluate the operational health of a machine.
Typical user requests
- Assess this machine
- Evaluate server health
- Is this machine healthy?
- Review system status
Expected output
- Overall machine assessment
- Resource utilization
- Operational issues
- Recommendations
---
## Application Discovery
Purpose
Determine whether an application exists on a target system.
Typical user requests
- Is Graylog installed?
- Does this server have Docker?
- Is Prometheus running?
- Is Nginx installed?
Expected output
- Installation status
- Running status
- Service information
- Discovery evidence
---
## Service Assessment
Purpose
Evaluate the health of one or more services.
Typical user requests
- Is SSH running?
- Check Docker service
- Is MySQL healthy?
- Review system services
Expected output
- Service status
- Availability
- Failures
- Recommendations
---
## Monitoring Assessment
Purpose
Evaluate monitoring platforms.
Typical user requests
- Are there any problems?
- Show monitoring status.
- Is anything critical?
- Review alerts.
Expected output
- Active problems
- Severity summary
- Monitoring coverage
- Operational impact
---
## Security Assessment
Purpose
Evaluate security posture.
Typical user requests
- Is SSH secure?
- Review firewall configuration.
- Check security settings.
- Evaluate hardening.
Expected output
- Security findings
- Risks
- Recommendations
---
## Performance Assessment
Purpose
Evaluate runtime performance.
Typical user requests
- Why is the server slow?
- Review performance.
- Check CPU usage.
- Check memory usage.
Expected output
- Bottlenecks
- Resource usage
- Performance risks
---
## Storage Assessment
Purpose
Evaluate storage health.
Typical user requests
- Check disk usage.
- Review filesystem.
- Is storage healthy?
- Any storage problems?
Expected output
- Capacity
- Utilization
- Filesystem status
- Storage risks
---
## Network Assessment
Purpose
Evaluate network connectivity.
Typical user requests
- Check networking.
- Review interfaces.
- Are there connection problems?
- Review ports.
Expected output
- Connectivity
- Interfaces
- Routing
- Network issues
---
## Configuration Assessment
Purpose
Review configuration quality.
Typical user requests
- Review SSH configuration.
- Check Docker configuration.
- Validate configuration.
- Inspect system settings.
Expected output
- Configuration summary
- Findings
- Recommendations
---
## Troubleshooting
Purpose
Investigate an operational problem.
Typical user requests
- Why isn't this working?
- Find the issue.
- Diagnose the problem.
- Help troubleshoot.
Expected output
- Root cause candidates
- Supporting evidence
- Confidence level
- Recommendations
---
# Intent Resolution Principles
Intent Resolution should:
- identify the user's investigation objective
- avoid ambiguity whenever possible
- remain deterministic
- avoid AI reasoning when simple rules are sufficient
---
# One Primary Intent
Every investigation should begin with one primary intent.
Example
```
Is Graylog installed on monitor?
```
↓
Primary Intent
```
Application Discovery
```
Target
```
monitor
```
The investigation should not become a Monitoring Assessment simply because Graylog is a monitoring application.
---
# Intent Is Not Capability
Intent describes **what** should be investigated.
Capabilities describe **how** evidence is collected.
Example
```
Intent
↓
Application Discovery
↓
Evidence Template
↓
Execution Graph
↓
Capabilities
```
The platform must never execute capabilities directly from the user request.
---
# Intent Is Stable
Intents represent operational objectives.
They should change rarely.
New intents should only be introduced when existing intents cannot represent a new investigation objective.
---
# Final Principle
The Intent Library exists to classify investigations, not to execute them.
Execution decisions belong to the Execution Pipeline.
Evidence collection belongs to Child Tools.
Assessment belongs to the Assessment Model.
