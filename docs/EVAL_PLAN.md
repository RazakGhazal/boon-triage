# Pre-registered evaluation plan — frozen on Day 14 (2025-10-14)

This plan is written **before Quiz 2 exists**. The metrics, definitions, and
analysis code (`scripts/eval_day20.py`) are frozen now so that the Day-20
readout cannot be shaped by the outcomes. No metric swaps, no post-hoc
subgroups; everything below gets reported.

## Definitions

- **Failer** — scored < 60 on Quiz 1. An exam-day absence (0 with a blank
  session) is not a failure; absentees are tracked separately.
- **Contact** — any dated facilitator note for the student, OR a row in the
  exported contact log (the queue page's "mark contacted" → CSV), in Days 11–19.
- **Assignment record** — the committed `outputs/queue.json` from the Day-14
  run: who was in the capped call list vs the call-waitlist vs messages. This
  file is the frozen treatment assignment; the eval never recomputes it.

## Primary metric (the KPI)

**% of Quiz-1 failers contacted in Days 11–19**, overall and per facilitator,
vs the Day-14 baseline measured from the same data (notes-only definition).
Success for the pilot = the gap between the two closes materially; the 80%
target is the program-level bar, not a two-day-pilot bar.

## Secondary (causal, quasi-experimental): RD at the capacity cutoff

The capped call list creates a regression discontinuity: among failers whose
recommended action was a call/1-on-1, students just inside the top-k and just
outside it (call-waitlisted — message today, call later) are near-identical in
risk; the cutoff is arbitrary at the margin. Compare mean Quiz-2 scores across
the cutoff within facilitator (±2 queue ranks). This estimates the *local*
added value of a call beyond a message — small-n and directional at 200
students, but it is a real identification strategy, and it scales.

## Guardrails (report all, always)

- Quiz-2 outcomes and contact rates **by track** (Remedial over-representation
  in the queue is expected and correct; unequal *contact* given queue membership
  is not).
- Contact rates **by facilitator note-coverage tier** — the operative equity
  axis in a notes-reading system: students of low-coverage facilitators must
  not be systematically under-served (facilitator8: 38 students, 16 failers,
  21% note coverage — watch this one).
- Absentees (exam-day 0s): followed up or not.

## Known contamination, named up front

Once the queue drives interventions, Quiz-2 outcomes are **post-treatment**:
naive forward validation of the risk score against Quiz 2 is biased downward
(successful interventions make true positives look like false alarms). The
risk ranking itself is validated *backward* instead (`--backtest`: Day-9 score
vs Quiz-1 failure), and forward causal claims come only from the RD above and
the rollout design below.

## Scale rollout = the experiment (20 → 100 campuses)

No within-campus holdout: denying triage to a live classroom to measure lift
is ethically wrong and, at k=1 cluster, statistically empty. Instead the
rollout **is** the experiment — a stepped wedge: randomize the order in which
campuses onboard (waves over ~6 months). Every campus eventually gets the
system; while waves differ, later waves are concurrent controls for earlier
ones. Intervention rate and quiz outcomes are compared within wave-time. This
costs nothing (100 campuses cannot launch simultaneously anyway) and gives the
program-level lift estimate a 200-student pilot never can.
