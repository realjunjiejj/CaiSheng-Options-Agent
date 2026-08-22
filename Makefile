.PHONY: install test test-fast demo cli-nvda cli-tsla cli-aapl

install:
	uv pip install --python .venv/bin/python -r requirements.txt

test:
	.venv/bin/pytest -v tests/

test-fast:
	.venv/bin/pytest -q tests/

demo:
	.venv/bin/streamlit run app.py

cli-nvda:
	.venv/bin/python cli.py --symbol NVDA

cli-tsla:
	.venv/bin/python cli.py --symbol TSLA

cli-aapl:
	.venv/bin/python cli.py --symbol AAPL
