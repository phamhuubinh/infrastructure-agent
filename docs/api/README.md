# API documentation

The API must expose product resources and typed runtime state, not leak internal provider protocol details.

OpenAPI is generated from the implemented backend after the new API stabilizes. This reset intentionally does not ship the previous `openapi.json` because it would incorrectly bless an old implementation contract.

See `../architecture/API_BACKEND.md` for target semantics.
