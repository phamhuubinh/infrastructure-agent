# Changelog

## Unreleased — Local-first Chat + Project architecture

Documentation reset:

- redefined Orion as a local-first AI technical workbench;
- made Chat the base runtime;
- defined Project as Chat plus project-scoped knowledge/RAG;
- removed manual tool selection from Chat and Project;
- made all registered tools automatically available to the model;
- made tool choice model-driven instead of Orion pre-routing;
- removed dynamic tool exposure/discovery from the target architecture;
- removed quota/rate-limit/budget layers from the core product architecture;
- documented current Knowledge/RAG, calculator, Internet, Linux, Grafana, and Zabbix tool families;
- documented installation, Docker, model, RAG, testing, and troubleshooting flows;
- removed `.clinerules` from the documentation package.
