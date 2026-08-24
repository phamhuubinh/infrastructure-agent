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
```

Normal message submission must not require the user to choose tools.

The backend should generate OpenAPI from implementation once endpoint contracts are stable.

See `../architecture/BACKEND_API.md`.
