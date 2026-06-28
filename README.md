# Boon Academy — Intervention Triage

Tells each facilitator **who to help first, and why** — a ranked, capacity-bounded action
queue — to lift the intervention rate from ~30% toward 80%+.

The edge: it **reads** the Arabic facilitator notes instead of just counting them. Rules score
risk from the numbers; Gemini reads each note thread for the *state* of any intervention; a
3-rule fusion corrects where they disagree (a failing intervention escalates; a working one is
demoted to free capacity). It then measures whether past interventions actually worked.

📹 **Video walkthrough:** `<ADD LOOM LINK>`

## Run
    make setup                  # install deps
    cp .env.example .env        # add your GEMINI_API_KEY
    make demo                   # full closed-loop run, LLM on -> outputs/
    make no-llm                 # rules-only baseline (no key needed)
    make lift                   # what the note-reader changed vs rules-only
    make test                   # 13 acceptance tests (the demo students)

## Outputs (outputs/)
`action_queue.html` (the product — open in a browser) · `queue.csv` · `queue.json` · plus the
closed-loop reports `effectiveness_report.json` · `fairness_report.json` · `v2_report.md`.

## Docs
ingest → risk (attendance/practice/quiz + collapse term) → notes (Gemini, faithfulness-checked)
→ decide (3 rules) → output. Keys/config via `.env`; "today" is `AS_OF_DATE`, not `now()`, so
runs reproduce; the LLM is one swappable module (KSA/local for PDPL).
Full map: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/MODEL_CARD.md](docs/MODEL_CARD.md).
