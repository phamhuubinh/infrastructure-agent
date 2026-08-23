# API Documentation

`openapi.json` is a generated snapshot of the **implemented backend API contract**. It is not a
target-architecture document and must not be hand-edited to make documentation appear consistent.

The accepted target architecture lives in `docs/architecture/` and `docs/decisions/`. If the
implemented API does not yet expose a target feature, record that as an implementation gap rather
than changing the generated schema by hand.

After an API-affecting code change:

1. update the backend contract and tests;
2. regenerate the schema through the repository target:

   ```bash
   make openapi
   ```

3. review the generated `docs/api/openapi.json`;
4. run relevant backend/API tests;
5. verify the schema matches actual runtime behavior.

Generated OpenAPI is implementation evidence. Architecture authority comes from the accepted ADRs;
neither source should be rewritten merely to hide a real mismatch.
