# Architecture

A small, legible pipeline: deterministic rules score risk from the numbers, an LLM reads the
Arabic facilitator notes (the one thing a rule can't do), and a thin fusion layer reconciles the
two into a two-tier action queue — calls capped, drafted messages uncapped, so every Quiz-1
failer leaves with a ready action. The LLM is an **extractor, not an oracle** — it turns prose
into a structured state; the rules still decide.

## Pipeline

```
data/*.csv ─► ingest ─► risk (NEED)     ┐
                │                        ├─► decide (3 rule families) ─► render ─► outputs/
                └─► notes (STATE, LLM)  ┘        │ drafts.py fills a template message
                                                 ▼ when there is no note to draft from
        measurement: backtest (Day-9) · extractor eval (gold set) · lift vs rules-only
                     effectiveness (descriptive) · fairness/coverage-equity
        pre-registered: docs/EVAL_PLAN.md + scripts/eval_day20.py (runs when quiz2.csv exists)
```

Entry paths (`main.py`): **`run`** (the queue) · **`run_v2`** (queue + the full measurement
layer) · `--lift` · `--backtest` · `--eval-extractor`.

## Module map (`src/`)

| File | Role |
|---|---|
| `config.py` | All constants — the case calendar, thresholds, capacity, model. Loads `.env`. (At 100 campuses the calendar becomes a per-campus data table; every date already flows from here.) |
| `ingest.py` | CSVs → `StudentRecord`. Every data trap handled once; notes kept **dated**; `to_llm_payload()` = notes only — no metrics, no PII. |
| `risk.py` | NEED — transparent score: attendance, median practice, quiz, **quiz absence**, trajectory-cliff. |
| `notes.py` | STATE — Gemini/NoLLM backends read each thread into state + blocker; evidence-required faithfulness gate; abstention; content-hash cache keyed by prompt version. |
| `drafts.py` | Deterministic Arabic template drafts (gender-safe MSA) for the un-noted majority — the cheap intervention is never blocked on note coverage. |
| `decide.py` | Fusion, 3 rule families: escalate failing/refused · de-escalate improving/explained (with metric + confidence guards) · human-review the ambiguous. |
| `output.py` | The product: two-tier per-facilitator queue with KPI counters, contact logging (localStorage + CSV export), `queue.csv/json`, `run_log.json` (stamps the invocation). |
| `backtest.py` | Day-9 backtest: pre-quiz score vs actual Quiz-1 failure (AUC / precision@k) — the ranking's label-supervised validation. |
| `eval_extractor.py` | Note-reader vs 75 human gold labels (`eval/`): κ, per-state P/R, confusion, guardrail stats. |
| `effectiveness.py` | Descriptive post-contact engagement labels, limitations attached (no control, regression to the mean). |
| `fairness.py` | Track audit (behavior-only features) + the operative axis: per-facilitator note-coverage equity. |
| `output_v2.py` | Writes `v2_report.md` + the JSON reports. |
| `pipeline.py` | Orchestration: `run`, `run_v2`, lift. No holdout — the causal designs are pre-registered in `docs/EVAL_PLAN.md` (RD at the capacity cutoff; stepped-wedge rollout). |

## Data contract

| File | Grain | Key fields | Traps handled |
|---|---|---|---|
| `student_metadata.csv` | 1 row / student | `student_id`, track, campus, facilitator, phone | corrupt `target_score` ignored; dirty phones normalized |
| `student_daily_metrics.csv` | 1 row / student / day | attendance min, practice count, quiz score | quiz `0` + blank session = *absence* (still worth risk points); carried-forward quiz deduped; blank ≠ 0 |
| `facilitator_notes.csv` | 1+ rows / student | `student_id`, date, Arabic `note_text` | **joined on `student_id` only**; dates preserved into the LLM payload |

## Reproducibility & safety

- **"Today" is `AS_OF_DATE`, not `now()`** — every run reproduces; all windows are relative to
  it (that same clock is what makes the Day-9 backtest a two-line time machine).
- **Config/keys via `.env` only** — nothing hardcoded; `.env` is gitignored.
- **PII** — the LLM sees note text only; names/phones never leave the machine; drafts use a
  local `{name}` placeholder; phones are masked in outputs.
- **LLM is one swappable module** — KSA-region / local model for PDPL without touching the
  pipeline. `--no-llm` runs the full rules-only baseline offline.
- **Committed outputs stay canonical** — `demo.sh` (the narrated video demo) runs in
  `outputs/demo-live/` (gitignored); only `make demo` writes `outputs/`.

See [MODEL_CARD.md](MODEL_CARD.md) for the extractor's measured quality and limits,
[EVAL_PLAN.md](EVAL_PLAN.md) for the pre-registered Day-20 readout, and
[technical-report.pdf](technical-report.pdf) for the design rationale and evidence base.
