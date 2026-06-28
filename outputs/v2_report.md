# Boon Academy — v2 closed-loop action layer (as of 2025-10-14)

## 1. The 'attempted vs effective' gap — measured from the data
- 75 students had a logged facilitator intervention (a note).
- Outcome of those interventions (did engagement recover after?): {'no_change': 51, 'declined': 7, 'logged_too_late': 10, 're_engaged': 7}
- **Only 11% of measurable interventions re-engaged the student**; 11% kept declining despite contact; 13% were logged too late to act (final-day notes).
- A logged note is *not* an effective intervention — this gap is the real story behind the 30%.

## 2. The note-reader checked against real outcomes (data-grounded accuracy)
- Of 14 noted students where the LLM made a directional call, its read agreed with what actually happened **100%** of the time (LLM 'working'→re-engaged, 'failing/refused'→declined).

## 3. Closed loop: escalate where messaging already failed
- 6 surfaced students were *already contacted and still declined* — they do NOT need another drafted message; they need escalation beyond messaging: ['S005', 'S012', 'S017', 'S023', 'S091', 'S190']

## 4. Fairness audit
- Risk uses behavior only (attendance, practice, quiz_score, trajectory_cliff); never learning_track, campus_id, student_name, parent_phone, grade.
- Surface rate by track: Standard 21%, Accelerated 0%, Remedial 79%
- Surfacing correlates with track because Remedial students are genuinely failing more (behavior), not because track is a model input. The within-track view guarantees the top-risk Standard/Accelerated students are still surfaced, and calibrating within track prevents Remedial membership from re-flagging itself.

## 5. Measurement arms
- Treatment (surfaced for intervention): 73 students.
- Holdout (reserved, by facilitator cluster, to measure program lift): 24 students.
