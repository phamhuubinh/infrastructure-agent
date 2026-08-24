# UI and UX

## Primary experience

The UI should make Orion feel like one conversational technical workspace.

Main concepts:

- Chat;
- Projects;
- Documents/knowledge;
- Settings/integrations.

## No tool picker

Chat composer and Project chat must not contain a required tool selector.

Avoid:

- tool checkboxes;
- "RAG mode";
- "Grafana mode";
- "Linux mode";
- per-message tool dropdowns.

The model chooses tools automatically.

## Tool transparency

Automatic tool use may still be visible:

```text
Searching project documents…
Querying Grafana…
Inspecting Linux host…
Searching Internet…
Calculating…
```

Users can inspect results/source references without managing orchestration.

## Project UX

Opening a Project should feel like opening a Chat workspace with project knowledge attached.

Project pages may show:

- project metadata;
- documents and ingestion status;
- project conversations;
- source references.

## Documents

The UI should show:

- upload state;
- parsing/indexing state;
- failure reason;
- document metadata;
- deletion;
- source/citation navigation.

## Settings

Settings may configure:

- model endpoint/provider;
- embeddings/reranker;
- Internet integration;
- Linux targets/credentials;
- Grafana;
- Zabbix;
- storage paths.

These are application/integration settings, not per-chat tool choices.
