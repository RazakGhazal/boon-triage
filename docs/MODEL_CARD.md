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

**Inputs / privacy:** the model receives the note text ONLY — no attendance, practice,
or quiz numbers. That is deliberate twice over: metrics in the prompt would let the
state echo the numbers (contaminating the fusion and any note-vs-outcome comparison),
and it keeps the payload minimal. Roster names and parent phones are never sent
(`to_llm_payload`); drafts use a literal `{name}` placeholder filled locally.

**Measured quality (all 75 noted threads, human gold labels — `eval/`):**

| Prompt | strict | lenient | κ (state) | blocker | failing recall |
|---|---|---|---|---|---|
| v3   | 80% | 89% | 0.68 | 71% | 0.15 |
| v3.1 | **88%** | **99%** | **0.82** | 71% | 0.54 strict / 1.00 lenient |

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
