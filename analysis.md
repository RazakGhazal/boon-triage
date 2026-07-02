# Analysis

## 1. Diagnosis
The 30% is a **triage-and-cost** problem, not a motivation one: facilitators can't tell who to
help first, and each intervention is expensive enough that ranking alone can never reach 80% —
the largest classroom has **16 quiz-failers**, so any flat top-8 list caps its coverage at 50%
forever. The signal facilitators need is split between LMS numbers and their own free-text
Arabic notes, and nobody reads both together. So the system fuses both into a per-facilitator
queue that caps only the *expensive* actions (calls, 1-on-1s), ships a ready WhatsApp draft for
**every** failer, and shows each facilitator one number: failers reached before Quiz 2.

## 2. What I found in the data
- **The KPI, measured, not assumed:** 66 of 200 students failed Quiz 1; only **29 (44%)** have
  any logged contact since the quiz — ranging **20%→67% by facilitator** — and of 75 logged
  contact threads, only **11%** were followed by re-engagement (descriptive: no control group,
  and notes are written at dips, which revert).
- **Track almost determines outcome:** **88%** of Remedial students failed Quiz 1 (51/58 — the
  one exam-day absentee is an absence, not a 52nd failure) vs **0%** of Accelerated (0/14).
  Remedial fails as a *cohort*, not as scattered individuals.
- **The data itself is the ceiling:** 62% of students have *no note at all*; coverage swings
  21%→55% by facilitator and the biggest classroom (38 students, 16 failers) is the *least*
  documented — so a notes-only view is blindest exactly where load is highest. And the quiz is
  one lump-sum score: I learn *that* a student failed, never *which concepts*.

## 3. What I built and why
- **Ingest** that survives the real mess: joins on `student_id` only, treats a quiz "0" with a
  blank session as absence (still worth risk points — test avoidance is a flag), ignores the
  corrupt `target_score`, normalizes dirty phones, and keeps every note **dated**.
- **A transparent risk score (NEED)** — attendance, *median* practice (cram spikes don't
  count), quiz, absence, and a collapse term — **backtested**: scored on days 1–9 only, it
  ranks who actually failed Quiz 1 at **AUC 0.91** (precision@66 = 0.85).
- **A note-reader (STATE)** — Gemini turns each Arabic thread into a 6-state label + blocker,
  quoting a verbatim evidence span (unevidenced or fabricated claims are auto-downgraded to
  human review). Measured against **75 human gold-labeled threads**: **κ = 0.82** (88% strict,
  99% lenient) — and the gold set earned its keep by catching a failing-recall bug (0.15) that
  one prompt revision fixed (κ 0.68 → 0.82).
- **Fusion, three rule families:** failing/refused contact escalates (≥High); improving with
  agreeing numbers hands capacity back; an *explained* absence (sick, parent already engaged)
  becomes a check-in message instead of burning a call slot; low-confidence reads go to a human.
  Net effect: the notes moved **18 of 75** noted students (9 up, 8 down, 1 to review).
- **The product:** a two-tier queue (`action_queue.html` — calls capped, messages uncapped, so
  **66/66 failers leave with a ready action**), per-facilitator coverage counters, tap-to-log
  contact with CSV export, and a **pre-registered Day-20 eval** (`docs/EVAL_PLAN.md`) frozen
  before Quiz-2 outcomes exist.

## 4. What I cut and why
- **No live dashboard / web service.** A static page generated from committed outputs can't
  break in a demo and needs no server. For a 2-day build, an artifact that always runs beats a
  service that might.
- **No holdout group and no auto-learned weights.** Denying triage to a live classroom to
  measure lift is ethically wrong and statistically empty at one cluster; and with one quiz
  cycle there are no labels worth fitting. Instead the *rollout is the experiment*: a
  stepped-wedge onboarding order for 20→100 campuses, plus a regression-discontinuity readout
  at the capacity cutoff — both pre-registered, both free.

## 5. What I'd build next
The biggest lever is not a smarter model — it is **better data**. I'd keep the free-text notes
(that mess is exactly what the LLM tolerates) but add **one** structured field per contact —
"did it land?" — turning effectiveness from an uncontrolled proxy into ground truth the next
cycle can learn from; and I'd instrument the quiz **per question**. That unlocks what today's
data cannot support: knowing a student is weak on quadratics, not merely "at risk" — and a
queue that recommends *what to teach*, not just *who to call*. The smartest engineering move
here isn't a better classifier; it's knowing what to ask the data to become.
