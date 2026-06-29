# Discovery Engine Behavior
---
# Discovery Cycle
The Discovery Engine performs the following sequence:
1. Receive observations.
2. Validate observations.
3. Start discovery.
4. Construct structured knowledge.
5. Submit knowledge updates.
6. Report completion.
---
# Validation
Invalid observations terminate the discovery cycle.
No knowledge updates are submitted.
The Discovery Engine reports discovery diagnostics.
No retry is performed.
---
# Knowledge Construction
Knowledge construction transforms observations into structured knowledge.
The Discovery Engine does not interpret operational intent.
The Discovery Engine does not perform reasoning.
---
# Knowledge Submission
Knowledge updates are submitted through the defined Knowledge Model contracts.
Persistence belongs to the Knowledge Model.
---
# Failure Behavior
Failures produce discovery diagnostics.
The Discovery Engine remains available for future discovery cycles.
---
# Architectural Rules
The Discovery Engine:
* never performs planning;
* never executes actions;
* never modifies Runtime state;
* never owns persistent knowledge;
* never bypasses architectural contracts.
