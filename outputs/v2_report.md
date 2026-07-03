# Boon Academy — v2 measurement & audit (as of 2025-10-14)

## 1. The KPI, measured from the data
- **66 students failed Quiz 1.** Only **29 (44%)** have any logged contact since the quiz, with 6 days left to Quiz 2 — and the per-facilitator range is 20%–67%. That measured gap is the problem statement, reproduced from the raw data.
- Under the two-tier queue, **66/66 failers have a ready action today** (57 calls/1-on-1s capped at 8 per facilitator; 21 drafted messages, uncapped; 1 human-review). Messages are never capped — a fixed top-8 list would cap facilitator8 (16 failers) at 50% coverage forever.

## 2. Does the ranking point the right way? (Day-9 backtest)
- Scoring every student on days 1–9 only (pre-quiz clock) and checking against who actually failed Quiz 1: **AUC 0.911**, precision@66 = 0.85, and 56% of eventual failers were already surfaced (Medium+) the day before the quiz.
- Are hand-set weights naive? Measured: equal weights score 0.909 (≈ tuned — the design is weight-insensitive), while a 5-fold-CV logistic on the raw features reaches **0.976** — the price of binarizing signals into legible flags, paid deliberately (one label event; a facilitator must understand why #1 is #1) and reclaimable via Quiz-2 recalibration.
- Scope: validates the behavior terms only (attendance/practice/cliff); the quiz term cannot be backtested against the same quiz.

## 3. Is the note-reader reading right? (gold-set eval)
- Against 75 human-labeled threads (labeled from the notes only, before this extractor version ran — eval/CODEBOOK.md): **87% strict / 97% lenient agreement, Cohen's κ = 0.8** on the 6-state label; blocker agreement 69%.
- Guardrails in operation: 1 faithfulness-gate trips (non-'none' state without a verbatim Arabic span), 1 low-confidence abstentions → human-review lane.
- Remaining disagreements (2) are listed in outputs/extractor_eval.json for qualitative review.

## 4. What reading the notes changed (vs rules-only)
- The notes changed the outcome for **18 of 75 noted students**: 8 escalated, 9 de-escalated (capacity handed back), 1 routed to human review.
  - S004: High/queue → Critical/queue (failing) — “احمد لسا على نفس الوضع. حاولت اتواصل مع الاهل بدون نتيجة”
  - S006: Medium/queue → Low/leave_alone (explained) — “قال في مشكله عائليه - راح ترجع الاسبوع الجاي ان شاء الله”
  - S008: Low/leave_alone → High/queue (refused) — “الام كانت دفاعية: 'هي تحضر الحصص، ايش اكثر من كذا تبون؟' مو متعاونه”
  - S012: Critical/queue → Medium/queue (explained) — “ما كان يدري عن البرنامج اصلاً!”
  - S013: Low/leave_alone → Medium/human_review (needs_help) — “”

## 5. Contact ≠ effect (descriptive only — limitations attached)
- Of 75 students with logged contact: {'no_change': 51, 'declined': 7, 'logged_too_late': 10, 're_engaged': 7}. Only 11% of measurable threads re-engaged; 13% were logged too late to act.
- This is NOT a causal estimate — no control group, and regression to the mean (notes are written at dips) biases post-note movement. What it does show: **from current logs we cannot tell whether contact works** — which is exactly the argument for the one-field outcome log ('did it land?') in the roadmap.

## 6. Escalate: contacted and still declining
- 7 surfaced students were already contacted and kept declining — they need a call/1-on-1, not another message: ['S005', 'S012', 'S017', 'S023', 'S091', 'S123', 'S190']

## 7. Fairness & coverage equity
- Risk uses behavior only (attendance, practice, quiz_score, quiz_absence, trajectory_cliff); never learning_track, campus_id, student_name, parent_phone, grade.
- Surface rate by track: Standard 22%, Accelerated 0%, Remedial 88%.
- Remedial over-representation in the queue reflects behavior (88% of Remedial failed Quiz 1 vs 0% Accelerated), not a track input — expected, and correct for triage. The within-track view keeps other tracks' top risks reviewable.
- The operative equity risk is note coverage by facilitator (21%–55%): note-informed care must not concentrate where documentation is best. Un-noted students keep full rules scoring + template drafts, and every un-noted card carries a log-one-line nudge to close the coverage gap.
- Per-facilitator coverage (students / failers / note coverage / failers contacted since quiz): facilitator1 20/6/55%/67%; facilitator2 20/5/45%/20%; facilitator3 35/11/51%/45%; facilitator4 22/7/41%/43%; facilitator5 20/5/45%/40%; facilitator6 24/8/25%/50%; facilitator7 21/8/24%/38%; facilitator8 38/16/21%/44%

## 8. What happens on Day 20 (pre-registered)
- Primary: failer contact rate in days 11–19 vs the baseline in §1. Secondary: RD at the capacity cutoff (call vs message at the margin). Rollout to 100 campuses is a stepped wedge — the deployment order is the experiment. Frozen in docs/EVAL_PLAN.md; runs via `python scripts/eval_day20.py --quiz2 data/quiz2.csv`.
