# VedaCore API Docs Index

This repository contains the lean, production-ready VedaCore API. Extended runbooks live in the monorepo.

- Local Dev: see `/README.md` (Local Dev Quickstart)
- Production Env: see `/README.md` (Environment Model, Production Quickstart)
- CI/CD Workflows: `.github/workflows/ghcr-build.yml`, `deploy.yml`

External runbooks (monorepo):
- Lean API Strategy & Deploy: https://github.com/Sbrg33/vedacore/blob/main/vedacore/docs/feedback/8302025/LEAN_API_STRATEGY_AND_DEPLOY_PLAN.md
- PM Secrets & Deploy Checklist: https://github.com/Sbrg33/vedacore/blob/main/vedacore/docs/feedback/8302025/PM_SECRETS_AND_DEPLOY_CHECKLIST.md
- Go-Live Test Plan: https://github.com/Sbrg33/vedacore/blob/main/vedacore/docs/feedback/8302025/GO_LIVE_TEST_PLAN.md

GHCR image: `ghcr.io/<OWNER>/vedacore-api:<tag>`
- Tags: `sha-<commit>` (always), `latest` on main, release tags as created

