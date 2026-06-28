# Architecture

A small, legible pipeline: deterministic rules score risk from the numbers, an LLM reads the
Arabic facilitator notes (the one thing a rule can't do), and a thin fusion layer reconciles the
two into a ranked, capacity-bounded action queue. The LLM is an **extractor, not an oracle** — it
turns prose into a structured state; the rules still decide.

## Pipeline

```
data/*.csv ─► ingest ─► risk (NEED)  ┐
                │                     ├─► decide (3-rule fusion) ─► render ─► outputs/
                └─► notes (STATE,LLM) ┘
                                        v2 add-ons: effectiveness · fairness · holdout
```

Two entry paths (`main.py`):
- **`run`** — the core queue (ingest → risk → notes → decide → render).
- **`run_v2`** — the closed loop: same queue, plus the retrospective effectiveness grade, the
  data-grounded LLM-vs-outcome check, a facilitator-cluster holdout, and a fairness audit.

## Module map (`src/`)

| File | Role |
|---|---|
| `config.py` | All constants in one place — dates (`AS_OF_DATE`), thresholds, capacity, model name. Loads `.env`. |
| `ingest.py` | CSVs → `StudentRecord`. Handles every data trap; `to_llm_payload()` strips PII before the model. |
| `risk.py` | NEED — transparent risk score from attendance, median practice, quiz, and a trajectory-cliff term. |
| `notes.py` | STATE — `GeminiBackend` / `NoLLMBackend` read each note thread into a structured state; faithfulness + abstention guards; content-hash cache. |
| `decide.py` | The 3-rule fusion (escalate failing · demote working · human-review the ambiguous). Masks phones. |
| `output.py` | Renders the queue → `action_queue.html` (the product) + `queue.csv` / `queue.json` / `run_log.json`. |
| `effectiveness.py` | Grades each past intervention against what engagement did next (re-engaged / no-change / declined / too-late). |
| `fairness.py` | Audit: surface rate by track, within-track top-risk, declares features used vs sensitive-excluded. |
| `output_v2.py` | Writes the v2 reports (`effectiveness_report.json`, `fairness_report.json`, `llm_vs_outcome.json`, `v2_report.md`). |
| `pipeline.py` | Orchestration: `run`, `run_v2`, `compute_lift`, holdout + LLM-vs-outcome helpers. |

## Data contract

| File | Grain | Key fields | Traps handled |
|---|---|---|---|
| `student_metadata.csv` | 1 row / student | `student_id`, track, campus, facilitator, phone | corrupt `target_score` ignored; dirty phones normalized |
| `student_daily_metrics.csv` | 1 row / student / day | attendance min, practice count, quiz score | quiz `0` + blank session = *absence*, not failure; carried-forward quiz deduped; blank ≠ 0 |
| `facilitator_notes.csv` | 1+ rows / student | `student_id`, date, Arabic `note_text` | **joined on `student_id` only** — names in notes don't match the roster |

## Reproducibility & safety

- **"Today" is `AS_OF_DATE`, not `now()`** — every run reproduces; recency windows are relative to it.
- **Config/keys via `.env` only** — nothing hardcoded; `.env` is gitignored.
- **PII** — the LLM never sees names or phones; phones are masked in outputs; the fairness audit
  never uses a sensitive attribute as a model input.
- **LLM is one swappable module** (`LLMBackend`) — swap to a KSA-region / local model for PDPL
  without touching the rest of the pipeline. `--no-llm` runs the full rules-only baseline offline.

See [MODEL_CARD.md](MODEL_CARD.md) for the model's intended use, guardrails, and limits, and
[technical-report.pdf](technical-report.pdf) for the full design rationale and the evidence base.
