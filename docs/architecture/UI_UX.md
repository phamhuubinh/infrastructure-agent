# UI and UX

## Chat

One agent experience with conversation, execution mode, activity, approvals, evidence details, and actionable failures.

Every in-flight generation, abort operation, idle timer, and response update is bound to exact session ID + generation token. A timer from session A must never abort/rewrite B.

A drop/attachment affordance must actually upload/bind the file to the intended session with visible progress/error, or not advertise attachment.

## Models

Settings distinguish not-configured/configured-unknown/healthy/unhealthy. Failed tests must not leave a model presented as healthy.

## Destructive actions

Session/model/Project/document destructive actions require explicit confirmation before mutation. Cancel means no request/mutation; exact target is named; duplicate confirmation is disabled while pending.

## Diagnostics

Target UI activity derives from the same structured event stream as technical diagnostics. Show explicit action/status/evidence, never hidden chain-of-thought.
