# API Documentation

API documentation is generated from the implemented backend schema.

During the architecture refactor, the narrative target design lives in the
other documents under `docs/`. The generated OpenAPI snapshot may temporarily
reflect the pre-refactor implementation until the corresponding backend changes
land.

After each API-affecting migration step:

1. update the backend contract;
2. update tests;
3. regenerate `openapi.json` using the repository's canonical generation path;
4. verify the generated schema matches runtime behavior.

Do not hand-edit generated API schemas to make them appear consistent with the
target architecture.
