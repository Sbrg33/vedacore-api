# Minimal Makefile for vedacore-api

.PHONY: install run test smoke-local docker-build docker-run docker-stop docker-logs docker-smoke

install:
	python -m pip install --upgrade pip
	pip install -r requirements.txt

run:
	PYTHONPATH=./src:. uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload

test:
	PYTHONPATH=./src:. pytest -v --tb=short

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
