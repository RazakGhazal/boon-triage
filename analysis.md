# Analysis

## 1. Diagnosis
The 30% is a **triage** problem, not a motivation one: facilitators are overwhelmed and can't
tell *who to help first*. The signal is split between LMS numbers and their own free-text Arabic
notes, and nobody reads both together. Two facts sink the naive fixes: attendance is deceptive
(students attend fully and still fail), and **a logged note is not a successful intervention**.
So the system fuses both signals into a ranked, capacity-bounded queue — who to help first, and
why — then measures whether the help actually worked.

## 2. What I found in the data
- **Track almost determines outcome:** 90% of Remedial students failed Quiz 1 (52/58) vs **0%**
  of Accelerated (0/14). Remedial is failing as a *cohort*, not as scattered individuals.
- **Attempted ≠ effective:** of 75 logged interventions, only **11%** re-engaged the student;
  11% kept declining despite contact and 13% were logged on the final day, too late to act. That
  gap — not a lack of caring — is the real story behind the 30%.
- **The data itself is the ceiling:** 62% of students have *no note at all* (and 30% of
  quiz-failers are invisible to any notes-based view); among the notes that do exist, facilitator
  coverage swings 21%→55% and the largest classroom is the least documented. And the quiz is a
  single lump-sum score — I learn *that* a student failed, never *which concepts*.

## 3. What I built and why
- **Ingest** that survives the real mess: joins on `student_id` only (names in notes don't match
  the roster), treats a quiz "0" with a blank session as an *absence* not a failure, ignores a
  corrupt `target_score`, normalizes dirty phones.
- **A transparent risk score (NEED)** from legible signals — attendance, *median* practice (so a
  cram spike isn't rewarded), quiz — plus a *trajectory* term flagging a strong attendant who
  collapses to near-zero: the silent dropout the quiz can't catch.
- **A note-reader (STATE)** — Gemini reads each Arabic note thread into a small structured state
  (working / failing / refused / needs-help) with the exact Arabic span as evidence
  (faithfulness-checked; low-confidence reads abstain to a human). It extracts, it does not score
  — and it re-prioritized **13 of 75** noted students that the numbers alone got wrong.
- **A 3-rule fusion** for where numbers and notes disagree: a failing intervention escalates, a
  working one is demoted to free capacity, an ambiguous note goes to human review. Plus an
  **effectiveness loop** (grading past interventions against what engagement did next) and a
  fairness audit (risk uses behavior only — never track, campus, or grade).
- **The product:** a per-facilitator, capacity-bounded action queue (`action_queue.html` +
  CSV/JSON) with the story, the recommended action, and a drafted WhatsApp message.

## 4. What I cut and why
- **No live dashboard / web service.** The product is a static page generated from committed
  outputs — it can't break in a demo and needs no server. For a 2-day build, an artifact that
  always runs beats a service that might.
- **No auto-recalibration / online learning.** With one quiz cycle and no labeled outcomes,
  learned weights would be guesswork; the system *logs* what it flags so the loop can be built
  once real outcomes exist.

## 5. What I'd build next
The biggest lever here is not a smarter model — it is **better data**. On notes this sparse and a
single lump-sum quiz score, even perfect logic can only see each student from a kilometre up. I'd
(1) keep the free-text notes — that mess is exactly what the LLM tolerates, so I would *not* force
rigid forms — but add **one** structured field per contact ("did it land?"), turning the
effectiveness metric from a proxy into ground truth; and (2) instrument the quiz **per question**.
That unlocks what this data can't support today: true per-student diagnosis — knowing a student is
weak on quadratics, not merely "at risk" — and targeted remediation. The smartest engineering move
isn't a better classifier on this data; it's knowing what to ask the data to become.
