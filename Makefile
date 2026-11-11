PYTHON ?= python3
VENV_PYTHON := $(if $(wildcard .venv/Scripts/python.exe),.venv/Scripts/python.exe,.venv/bin/python)

.PHONY: setup dev build run test test-e2e docker-run docker-stop

setup:
	$(PYTHON) scripts/setup.py

dev:
	$(VENV_PYTHON) scripts/dev.py

build:
	npm --prefix frontend run build

run: build
	cd backend && ../$(VENV_PYTHON) -m app

test:
	cd backend && ../$(VENV_PYTHON) -m pytest
	npm --prefix frontend run check
	npm --prefix frontend test

test-e2e: build
	npm --prefix frontend run test:e2e

docker-run:
	docker compose up --build -d --wait

docker-stop:
	docker compose down

