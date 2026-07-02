.PHONY: setup demo queue no-llm lift backtest eval test
PYTHON ?= python3

setup:
	$(PYTHON) -m pip install -r requirements.txt

demo:          ## full run + measurement layer, LLM on -> outputs/ (needs GEMINI_API_KEY)
	$(PYTHON) main.py --v2

queue:         ## just the action queue, LLM on (no measurement reports)
	$(PYTHON) main.py

no-llm:        ## rules-only baseline (no key needed)
	$(PYTHON) main.py --no-llm

lift:          ## quantify what the note-reader changed vs rules-only
	$(PYTHON) main.py --lift

backtest:      ## Day-9 ranking backtest vs Quiz-1 outcomes (no LLM needed)
	$(PYTHON) main.py --backtest

eval:          ## note-reader vs the 75 human gold-labeled threads (uses cache)
	$(PYTHON) main.py --eval-extractor

test:          ## 22 acceptance tests (traps, fusion guards, KPI invariants)
	$(PYTHON) tests/test_cast.py
