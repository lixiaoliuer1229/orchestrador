.PHONY: install dev test lint format run docker-up docker-down clean

PYTHON ?= python3
PIP ?= $(PYTHON) -m pip

install:
	$(PIP) install -r requirements.txt

dev:
	$(PIP) install -e .

test:
	pytest tests/ -v

lint:
	ruff check src/ tests/ examples/
	mypy src/

format:
	black src/ tests/ examples/
	ruff check --fix src/ tests/ examples/

run:
	$(PYTHON) examples/hello_graph.py

docker-up:
	docker compose up -d

docker-down:
	docker compose down

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage data/
	find . -type d -name "__pycache__" -exec rm -rf {} +