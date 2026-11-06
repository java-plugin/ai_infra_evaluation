.PHONY: help sync lint test type check clean tco smoke

help:
	@echo "ai-infra-advisor"
	@echo ""
	@echo "  make sync     install deps with uv"
	@echo "  make lint     ruff check + format"
	@echo "  make type     mypy strict"
	@echo "  make test     pytest with coverage"
	@echo "  make check    lint + type + test"
	@echo "  make tco      smoke: ai-infra tco 64 H100 3y 60%"
	@echo "  make clean    remove caches"

sync:
	uv sync --all-extras

lint:
	uv run ruff check .
	uv run ruff format --check .

type:
	uv run mypy src tests

test:
	uv run pytest --cov=ai_infra --cov-report=term --cov-report=xml

check: lint type test

tco:
	uv run ai-infra tco --nodes 8 --gpus-per-node 8 --gpu h100-sxm5-80gb --years 3 --util 60

api:
	uv run uvicorn ai_infra.api.main:app --reload --port 8000

web:
	npm --prefix web run dev

build-web:
	npm --prefix web run build

clean:
	powershell -Command "Get-ChildItem -Recurse -Directory -Force -ErrorAction SilentlyContinue | Where-Object { $$_.Name -eq '__pycache__' -or $$_.Name -eq '.ruff_cache' -or $$_.Name -eq '.mypy_cache' -or $$_.Name -eq '.pytest_cache' } | Remove-Item -Recurse -Force"
