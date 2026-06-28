.PHONY: setup demo queue no-llm lift test
PYTHON ?= python3

setup:
	$(PYTHON) -m pip install -r requirements.txt

demo:          ## full closed-loop run, LLM on -> outputs/ (queue + effectiveness/fairness; needs GEMINI_API_KEY)
	$(PYTHON) main.py --v2

queue:         ## just the action queue, LLM on (no v2 reports)
	$(PYTHON) main.py

no-llm:        ## rules-only baseline (no key needed)
	$(PYTHON) main.py --no-llm

lift:          ## quantify what the note-reader changed vs rules-only
	$(PYTHON) main.py --lift

test:          ## 13 acceptance tests (the demo students)
	$(PYTHON) tests/test_cast.py
