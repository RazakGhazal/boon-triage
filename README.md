# Boon Academy — Intervention Triage

Tells each facilitator **who to help first, and why** — a two-tier action queue (calls
capped at 8, drafted messages uncapped) that hands every Quiz-1 failer a ready action —
to lift the intervention rate from ~30% toward 80%+.

The edge: it **reads** the Arabic facilitator notes instead of just counting them. Rules
score risk from the numbers (Day-9 backtest: **AUC 0.91**); Gemini reads each note thread
into a structured state (**κ=0.82** vs 75 human gold labels); a 3-family fusion corrects
where they disagree. Every claim quotes a verbatim Arabic span or goes to human review.

📹 **Video walkthrough:** `<ADD LOOM LINK>`

## Run
    make setup                  # install deps
    cp .env.example .env        # add your GEMINI_API_KEY
    make demo                   # full run + measurement layer, LLM on -> outputs/
    make no-llm                 # rules-only baseline (no key needed)
    make lift                   # what the note-reader changed vs rules-only
    make backtest               # Day-9 ranking vs Quiz-1 outcomes (no LLM)
    make eval                   # note-reader vs the human gold labels
    make test                   # 22 acceptance tests

## Outputs (outputs/)
`action_queue.html` (the product) · `notes_lift.html` (with vs without the LLM, side by side)
· `queue.csv/json` · `v2_report.md` · `extractor_eval.json` · `backtest_day9.json` · audits.

## Docs
[ARCHITECTURE](docs/ARCHITECTURE.md) · [MODEL_CARD](docs/MODEL_CARD.md) ·
[EVAL_PLAN](docs/EVAL_PLAN.md) (pre-registered Day-20 readout) · gold labels + codebook: `eval/`.
