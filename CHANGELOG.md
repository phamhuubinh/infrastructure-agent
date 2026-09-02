# Changelog

## Unreleased — Local-first Chat + Project architecture

Architecture and implementation alignment:

- redefined Orion as a local-first AI technical workbench;
- made Chat the base runtime;
- defined Project as Chat plus project-scoped knowledge/RAG;
- removed manual tool selection from Chat and Project;
- made every registered/configured ordinary tool discoverable to the model through the canonical registry;
- accepted registry-derived progressive model-facing schema exposure in ADR 0007 via the generic `orion.tools.expand` control;
- kept semantic tool choice model-driven instead of Orion pre-routing;
- kept canonical registry validation, `ToolRunner`, `RuntimeScope`, and execution permissions independent of request-local schema exposure;
- removed product-level quota/rate-limit layers from the core tool architecture while retaining bounded failure/watchdog safety mechanisms;
- documented current Knowledge/RAG, calculator, Internet, Linux, Grafana, and Zabbix tool families;
- documented installation, model, RAG, testing, and troubleshooting flows;
- removed `.clinerules` from the documentation package.
