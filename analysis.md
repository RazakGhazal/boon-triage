# Analysis

## 1. Diagnosis
The 30% is a **triage-and-cost** problem, not a motivation one: facilitators can't tell who to
help first, and each intervention costs enough that ranking alone can never reach 80% — the
largest classroom has **16 quiz-failers**, so any flat top-8 list caps its coverage at 50%
forever. The needed signal is split between LMS numbers and free-text Arabic notes nobody reads
together. So the system fuses both into a per-facilitator queue that caps only the *expensive*
actions, ships a ready WhatsApp draft for **every** failer, and shows each facilitator one
number: failers reached before Quiz 2.

## 2. What I found in the data
- **The KPI, measured, not assumed:** 66 of 200 students failed Quiz 1; only **29 (44%)** have
  any logged contact since — ranging **20%→67% by facilitator** — and of 75 logged contact
  threads, only **11%** were followed by re-engagement (descriptive: no control group, and
  notes are written at dips, which revert).
- **Track almost determines outcome:** **88%** of Remedial failed (51/58 — the one exam-day
  absentee is an absence, not a 52nd failure) vs **0%** of Accelerated. Remedial fails as a
  *cohort*, not as scattered individuals.
- **The data itself is the ceiling:** 62% of students have *no note*; coverage swings 21%→55%
  and the biggest classroom (38 students, 16 failers) is the *least* documented — a notes-only
  view is blindest exactly where load is highest. And the quiz is one lump-sum score: I learn
  *that* a student failed, never *which concepts*.

## 3. What I built and why
- **Ingest** that survives the mess: joins on `student_id` only, reads a quiz "0" with a blank
  session as absence (still worth risk points — test avoidance is a flag), ignores the corrupt
  `target_score`, normalizes dirty phones, keeps every note **dated**.
- **A transparent risk score, backtested:** scored on days 1–9 only, it ranks who actually
  failed Quiz 1 at **AUC 0.91**. Naive weights? Measured: equal weights score the same (0.909),
  and a CV logistic on raw features hits 0.976 — a gap paid deliberately for legibility on one
  label event, reclaimable by Quiz-2 recalibration.
- **A note-reader with a gold set:** Gemini turns each Arabic thread into a 6-state label +
  blocker, quoting a verbatim evidence span (unevidenced claims auto-drop to human review).
  Against **75 human-labeled threads**: **κ = 0.80** (87% strict / 97% lenient) — and the gold
  set caught a failing-recall bug (0.15) that one prompt revision fixed (κ 0.68 → 0.80;
  the two residual misses are documented gray cases).
- **Fusion, three rule families:** failing/refused contact escalates (≥High); improving with
  agreeing numbers hands capacity back; an *explained* absence (sick, parent already engaged)
  becomes a check-in message instead of burning a call slot; low-confidence reads go to a
  human. Net: notes moved **18 of 75** noted students (9 up, 8 down, 1 review).
- **The product:** a two-tier queue (`action_queue.html` — calls capped, messages uncapped, so
  **66/66 failers get a ready action**), coverage counters, tap-to-log contact with CSV export,
  and a **pre-registered Day-20 eval** (`docs/EVAL_PLAN.md`) frozen before Quiz-2 exists.

## 4. What I cut and why
- **No live dashboard / web service.** A static page generated from committed outputs can't
  break in a demo and needs no server; an artifact that always runs beats a service that might.
- **No holdout group, no auto-learned weights.** Denying triage to a live classroom is
  ethically wrong and statistically empty at one cluster; with one quiz cycle there are no
  labels worth fitting. Instead the *rollout is the experiment*: stepped-wedge onboarding for
  20→100 campuses plus a regression-discontinuity readout at the capacity cutoff — both
  pre-registered, both free.

## 5. What I'd build next
The biggest lever is not a smarter model — it is **better data**. Keep the free-text notes
(that mess is exactly what the LLM tolerates) but add **one** structured field per contact —
"did it land?" — turning effectiveness from an uncontrolled proxy into ground truth; and
instrument the quiz **per question**. That unlocks what today's data cannot support: knowing a
student is weak on quadratics, not merely "at risk" — a queue that recommends *what to teach*,
not just *who to call*. The smartest engineering move here isn't a better classifier; it's
knowing what to ask the data to become.
