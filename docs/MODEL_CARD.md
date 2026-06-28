# Model Card — the note-reader

**Model:** Gemini 2.5 Flash Lite (`gemini-2.5-flash-lite`), temperature 0, native
structured output (`responseSchema`). One swappable module behind `notes.py`.

**Job (extractor, not oracle):** read one student's facilitator-note thread (informal
Saudi-dialect Arabic) and return a small structured state — `state`
(none/on_track/needs_help/failing/refused), a one-line summary, root cause, a suggested
action, an Arabic WhatsApp draft, an evidence span, concern, and confidence. It does
**not** score risk or rank students — deterministic rules do that.

**Why an LLM here and nowhere else:** reading dialectal Arabic prose is the one job a
rule cannot do. Everything else (risk, fusion, ranking) is deterministic and explainable.

**Inputs / privacy:** the model receives note text + de-identified metrics only. Student
names and parent phone numbers are stripped before the prompt (`to_llm_payload`). Output
displays mask phone numbers.

**Guardrails:**
- *Faithfulness* — the quoted Arabic evidence must be a verbatim substring of a real
  note; fabricated quotes are dropped and the confidence downgraded to low.
- *Abstention* — low-confidence extractions are routed to a human-review lane, never
  auto-acted.
- *Determinism* — temperature 0 + content-hash cache keyed by prompt version, so runs
  reproduce.

**Known limitations:** notes cover only 75/200 students, so the LLM affects ~37% of the
roster; the rest are handled by rules. Dialect extraction quality is measured on a small
hand-labeled set — treat per-field accuracy as directional. `state` can be mislabeled on
genuinely ambiguous notes (mitigated by abstention).

**Production / PDPL:** for real minors' PII under PDPL, swap the note-reader to a
KSA-region Vertex deployment or a local model — it is the only component that touches the
LLM, so nothing else in the pipeline changes.

**Cost:** at ~5k students the annual note-reading bill on Flash Lite is low (order of
hundreds of USD/yr); verify current rates.
