# Minimal Makefile for vedacore-api

.PHONY: install run test test-fast test-parallel smoke-local docker-build docker-run docker-stop docker-logs docker-smoke check-health test-contracts clean clean-all

# Base URL for check-health (override: make check-health BASE=https://api.vedacore.io)
BASE ?= http://127.0.0.1:8000

install:
	python -m pip install --upgrade pip
	pip install -r requirements.txt

run:
	PYTHONPATH=./src:. uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload

test:
	VC_SKIP_WARMUP=1 NUMBA_DISABLE_JIT=1 PYTHONPATH=./src:. pytest -v --tb=short

# Even faster local run focused on unit + contracts, bails on first failure
test-fast:
	VC_SKIP_WARMUP=1 NUMBA_DISABLE_JIT=1 PYTHONPATH=./src:. pytest -x --tb=line tests/test_*.py tests/contracts/

# Parallel run (requires pytest-xdist). Falls back to sequential if plugin missing.
test-parallel:
	VC_SKIP_WARMUP=1 NUMBA_DISABLE_JIT=1 PYTHONPATH=./src:. pytest -n auto -v --tb=short \
	|| VC_SKIP_WARMUP=1 NUMBA_DISABLE_JIT=1 PYTHONPATH=./src:. pytest -v --tb=short

# Run OpenAPI/contract tests in chunks to avoid local timeouts
test-contracts:
	PYTHONPATH=./src:. pytest -q \
		tests/contracts/test_content_type.py \
		tests/contracts/test_openapi_contracts.py \
		tests/contracts/test_operation_ids.py \
		tests/contracts/test_openapi_headers.py
	PYTHONPATH=./src:. pytest -q \
		tests/contracts/test_paths_present.py \
		tests/contracts/test_sse_openapi.py \
		tests/contracts/test_timing_p95.py

smoke-local:
	@echo "💨 Local smoke: start API, check readiness, stop"
	@PYTHONPATH=./src:. uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 >/tmp/vedacore-smoke.log 2>&1 & echo $$! > /tmp/vedacore-smoke.pid; \
	 i=0; ok=0; \
	 while [ $$i -lt 20 ]; do \
	   if curl -fsS http://127.0.0.1:8000/api/v1/health/ready >/dev/null 2>&1; then ok=1; break; fi; \
	   i=$$((i+1)); sleep 1; \
	 done; \
	 if [ $$ok -eq 1 ]; then echo "✅ Ready"; else echo "❌ Not ready"; tail -n 120 /tmp/vedacore-smoke.log || true; fi; \
	 kill $$(cat /tmp/vedacore-smoke.pid) 2>/dev/null || true; \
	 rm -f /tmp/vedacore-smoke.pid /tmp/vedacore-smoke.log || true; \
	 test $$ok -eq 1

docker-build:
	docker build -t vedacore-api .

docker-run:
	@docker run -d --rm --name vedacore-api -p 8000:8000 \
	  -e AUTH_JWT_SECRET=dev-secret-for-local \
	  vedacore-api

docker-stop:
	-@docker rm -f vedacore-api >/dev/null 2>&1 || true

docker-logs:
	@docker logs -f vedacore-api

docker-smoke: docker-stop docker-build docker-run
	@echo "💨 Docker smoke: wait for readiness"
	@i=0; ok=0; \
	 while [ $$i -lt 30 ]; do \
	   if curl -fsS http://127.0.0.1:8000/api/v1/health/ready >/dev/null 2>&1; then ok=1; break; fi; \
	   i=$$((i+1)); sleep 2; \
	 done; \
	 if [ $$ok -eq 1 ]; then echo "✅ Ready"; else echo "❌ Not ready"; docker logs vedacore-api || true; fi; \
	 $(MAKE) docker-stop; \
	 test $$ok -eq 1

# Portable API health check (prefers /health/up, fallback /health/ready)
check-health:
	PYTHONPATH=./src:. python tools/check_api_health.py --base $(BASE) --json
export-openapi:
	@echo "Exporting OpenAPI schema to openapi.json"
	@python tools/export_openapi.py --base $(BASE) --out openapi.json

sdk-ts:
	@echo "Generating TypeScript SDK (requires Docker)"
	@docker run --rm -v "$(PWD)":/local openapitools/openapi-generator-cli:v7.6.0 generate \
	  -i /local/openapi.json -g typescript-fetch -o /local/sdk/ts \
	  -p useSingleRequestParameter=true,typescriptThreePlus=true,supportsES6=true,withSeparateModelsAndApi=true,npmName=@vedacore/api

sdk-python:
	@echo "Generating Python SDK (requires openapi-python-client)"
	@openapi-python-client generate --path openapi.json --meta setup --output-path sdk/python

# Cleanup helpers
clean:
	@echo "🧹 Cleaning caches and artifacts (safe)"
	@find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	@rm -rf .pytest_cache htmlcov coverage.xml

clean-all: clean
	@echo "🧹 Cleaning additional local venvs (.venv-*, keep .venv)"
	@rm -rf .venv-api .venv-ci .venv-validate
