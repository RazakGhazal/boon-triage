# Model Card — the note-reader

**Model:** Gemini 2.5 Flash Lite (`gemini-2.5-flash-lite`), temperature 0, native
structured output (`responseSchema`). One swappable module behind `notes.py`.

**Job (extractor, not oracle):** read one student's facilitator-note thread (short,
informal Saudi-dialect Arabic, dated `[Day N]`) and return a small structured state —
`state` (none / improving / explained / needs_help / failing / refused), a `blocker`
(academic / motivation / family / health / logistics / unknown), a one-line summary,
root cause, a suggested action, an Arabic WhatsApp draft (with a `{name}` placeholder
filled locally), a verbatim evidence span, concern, and confidence. It does **not**
score risk or rank students — deterministic rules do that.

**Why an LLM here and nowhere else:** reading dialectal Arabic prose is the one job a
rule cannot do. Everything else (risk, fusion, ranking, template drafts for un-noted
students) is deterministic and explainable.

**Inputs / privacy:** the model receives the note text + the student's gender ONLY —
no attendance, practice or quiz numbers, and never a name or phone. Metrics are
excluded so the state can't echo the numbers (that would contaminate the fusion and
any note-vs-outcome comparison). Gender (v3.2) is included because the draft is
written around a `{name}` placeholder and Arabic verbs/pronouns must agree with the
ROSTER child — names inside notes can belong to someone else (the name-mismatch
trap), so the model is instructed never to infer gender from them. The v3.2 re-run
moved two genuinely ambiguous threads (κ 0.82→0.80); both are in the disagreement
list, not hidden.

**Measured quality (all 75 noted threads, human gold labels — `eval/`):**

| Prompt | strict | lenient | κ (state) | blocker | failing recall |
|---|---|---|---|---|---|
| v3   | 80% | 89% | 0.68 | 71% | 0.15 |
| v3.1 | 88% | 99% | 0.82 | 71% | 0.54 strict / 1.00 lenient |
| v3.2 | **87%** | **97%** | **0.80** | 69% | 0.54 strict / 1.00 lenient |

Labels were drafted from the notes alone, **before** v3 ran, against a written codebook
(`eval/CODEBOOK.md`); genuinely two-way threads carry an adjudicated alternate state
(the "lenient" column). The gold set immediately earned its keep: v3 was reading
"student vanished + parents unreachable" as `needs_help` (no escalation) — failing
recall 0.15; one sharpened definition plus one few-shot fixed it (v3.1). Single-rater
labels: per-state numbers are directional at n=75, and a second Arabic-speaking rater
(for true inter-rater κ) is the top validation upgrade.

**Guardrails (operating stats from the committed run):**
- *Faithfulness* — every non-`none` state must quote a verbatim span from a real note;
  a missing OR fabricated quote is downgraded to low confidence (1 trip / 75).
- *Name-leak guard* — a draft that doesn't use the `{name}` placeholder copied a name
  from the notes (possibly the WRONG child's); it is discarded for the gender-safe
  deterministic template.
- *Abstention* — low-confidence reads route to a human-review lane, never auto-acted
  (1 / 75).
- *De-escalation guards* — `improving` can lower priority only if the metrics agree
  AND confidence isn't low; `explained` (sick, parent engaged) becomes a check-in
  message, never invisible while a quiz is failed.
- *Determinism* — temperature 0 + content-hash cache keyed by prompt version.

**Known limitations:** notes cover only 75/200 students — the audited coverage-equity
gap (`fairness_report.json`): the biggest classroom is the least documented, so the
product nudges a one-line log after every contact. `blocker` (71%) is genuinely fuzzier
than `state`. Truly ambiguous dialect can still mislabel (mitigated by abstention, the
review lane, and the evidence span shown on every card for a human to overrule).

**Production / PDPL:** for real minors' PII, swap the note-reader to a KSA-region
Vertex deployment or a local model — it is the only component that touches an external
API, so nothing else changes. Message *content* is also personal data: parent messaging
goes through WhatsApp Business API with recorded opt-in.

**Cost / latency:** ~75 short threads per run on Flash Lite costs well under $0.01
uncached; at 5,000 students (~40% noted, daily runs) the note-reading bill stays in the
hundreds of USD/yr. It's a batch job — latency is irrelevant to the product.
