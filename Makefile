.PHONY: help setup dev api web test lint fmt docker-up docker-down sandbox-image clean

help:
	@echo "setup         Install backend + frontend dependencies"
	@echo "dev           Run API and dashboard together"
	@echo "api           Run the FastAPI backend (reload)"
	@echo "web           Run the Next.js dashboard"
	@echo "test          Run backend tests"
	@echo "lint / fmt    Ruff lint / format"
	@echo "docker-up     Full stack via docker compose"
	@echo "sandbox-image Build the execution sandbox image"

setup:
	cd backend && python -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
	cd frontend && npm install
	cp -n backend/.env.example backend/.env || true

api:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

web:
	cd frontend && npm run dev

dev:
	$(MAKE) -j2 api web

test:
	cd backend && pytest -q

lint:
	cd backend && ruff check app tests

fmt:
	cd backend && ruff format app tests && ruff check --fix app tests

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

sandbox-image:
	docker build -t bhati-sandbox:latest ./sandbox

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} + ; rm -rf backend/.pytest_cache frontend/.next
