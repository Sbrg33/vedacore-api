## VedaCore API — High‑Level Overview

VedaCore API is a lean, production‑ready FastAPI service for high‑precision KP astrology. It exposes REST and streaming endpoints with strong health checks and deterministic deployments.

What you need to know
- Purpose: KP calculations and related endpoints (with optional streaming).
- Auth: JWT. REST uses Authorization: Bearer; streaming uses short‑lived tokens.
- Health: `/api/v1/health/up` and `/api/v1/health/ready` for monitoring.
- Deploy: Container images on GHCR; use immutable SHA tags.

Start here
- Development, deployment, and full details live in `README.md`.
- SDK usage and generation: see `SDK.md`.

This document intentionally omits deep technical details. Refer to `README.md` for configuration, endpoints, and runbooks.
