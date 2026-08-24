# API Documentation

`openapi.json` is a generated snapshot of the **implemented backend route/schema surface**. It is not target architecture and must not be hand-edited.

Several current handlers use generic `dict` request/response types, so generated OpenAPI contains `{}` or broad `additionalProperties` schemas. Therefore route/operation presence is implementation evidence, but a generic schema is not proof that the full runtime payload contract is statically described.

When a stable public payload matters, prefer typed endpoint models/tests so generated OpenAPI is precise.

After API-affecting changes:

```bash
make openapi
```

Then review the generated file, run relevant API tests, and verify runtime behavior matches it.
