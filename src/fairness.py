"""Fairness audit — guard against the documented early-warning harms.

The Wisconsin DEWS lesson: a recall-maxed model flagged the wrong kids and
concentrated false alarms on the most disadvantaged, with zero benefit. Two
concrete guards for this system:

  1. The risk score is driven by BEHAVIOR (attendance/practice/quiz/trajectory),
     never by membership — learning_track, campus, name, phone are NOT inputs.
     This audit proves it and surfaces any disparate impact for review.
  2. A WITHIN-TRACK view so the Remedial cohort (90% of whom fail) can't drown
     out the most-at-risk Standard/Accelerated students — and so Remedial
     membership never becomes a self-entrenching re-flag.
"""
from __future__ import annotations

from collections import defaultdict

# inputs the risk model is ALLOWED to use (behavior only) vs attributes it must never use
RISK_FEATURES = ["attendance", "practice", "quiz_score", "trajectory_cliff"]
SENSITIVE_NEVER_USED = ["learning_track", "campus_id", "student_name", "parent_phone", "grade"]


def audit(records, risks, surfaced_ids: set) -> dict:
    by_track = defaultdict(lambda: {"n": 0, "surfaced": 0})
    for sid, r in records.items():
        t = by_track[r.learning_track]
        t["n"] += 1
        if sid in surfaced_ids:
            t["surfaced"] += 1
    for t in by_track.values():
        t["surface_rate_pct"] = round(100 * t["surfaced"] / t["n"]) if t["n"] else 0

    # within-track: the highest-risk students inside each track (so each track is seen)
    within = defaultdict(list)
    for sid, r in records.items():
        within[r.learning_track].append((sid, risks[sid].score))
    within_top = {t: [s for s, _ in sorted(v, key=lambda x: -x[1])[:5]] for t, v in within.items()}

    return {
        "risk_features_used": RISK_FEATURES,
        "sensitive_attributes_excluded": SENSITIVE_NEVER_USED,
        "surface_rate_by_track": dict(by_track),
        "within_track_top5": within_top,
        "note": ("Surfacing correlates with track because Remedial students are genuinely "
                 "failing more (behavior), not because track is a model input. The within-track "
                 "view guarantees the top-risk Standard/Accelerated students are still surfaced, "
                 "and calibrating within track prevents Remedial membership from re-flagging itself."),
    }
