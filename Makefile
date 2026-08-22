PYTHON ?= $(shell which python3 || which python)
PYTEST ?= $(shell if [ -f .venv/bin/pytest ]; then echo .venv/bin/pytest; else which pytest; fi)

.PHONY: install test test-fast demo cli-nvda cli-tsla cli-aapl

install:
	pip install -e .
	pip install -r requirements.txt

test:
	$(PYTEST) -v tests/

test-fast:
	$(PYTEST) -q tests/

demo:
	streamlit run app.py

cli-nvda:
	python cli.py --symbol NVDA

cli-tsla:
	python cli.py --symbol TSLA

cli-aapl:
	python cli.py --symbol AAPL
