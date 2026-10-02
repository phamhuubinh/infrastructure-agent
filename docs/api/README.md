# API documentation

The API should expose product resources rather than the model's internal reasoning.

Target resource families:

```text
health
models
sessions/messages
attachments
projects
project documents
knowledge/document lifecycle
integrations/tool health
streaming events
scheduler tasks/history
```

Normal message submission must not require the user to choose tools.

The backend should generate OpenAPI from implementation once endpoint contracts are stable.

See `../architecture/BACKEND_API.md`.

The protected [Scheduler v1 API](../architecture/SCHEDULER.md#protected-api) derives
task scope from a visible session and bounds task/history result limits to 100.
