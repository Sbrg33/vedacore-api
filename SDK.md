SDK Generation Guide

Summary
- OpenAPI spec is exported to openapi.json
- Generate SDKs:
  - TypeScript (typescript-fetch)
  - Python (openapi-python-client)

Export the spec
- From a running API (preferred):
  - python tools/export_openapi.py --base http://127.0.0.1:8000 --out openapi.json
- From local import (requires deps):
  - python tools/export_openapi.py --local --out openapi.json

TypeScript SDK
- Using Docker (recommended):
  docker run --rm -v "$PWD":/local openapitools/openapi-generator-cli:v7.6.0 generate \
    -i /local/openapi.json -g typescript-fetch -o /local/sdk/ts \
    -p useSingleRequestParameter=true,typescriptThreePlus=true,supportsES6=true,withSeparateModelsAndApi=true,npmName=@vedacore/api

Python SDK
- pipx install openapi-python-client
- openapi-python-client generate --path openapi.json --meta setup --output-path sdk/python

CI Workflow
- See .github/workflows/sdk.yml for automated build/publish on tag.

Notes
- SSE endpoints use EventSource/websocket directly; SDKs don’t wrap streams.
- Auth: send X-API-Key header; streaming uses token flow via /api/v1/auth/stream-token.

Channels & policy

- Stable: Built from repo‑committed `openapi.json`. Published on `sdk-vX.Y.Z` tags. Semver enforced; breaking changes require a major.
- Next: Nightly from the live spec. Published as `@vedacore/api@next` (npm) and `vedacore-api==X.Y.Z.devYYYYMMDDHHMM` (PyPI). Expect churn.

Choose stable for production. Use next to test upcoming changes early.
