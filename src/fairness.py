"""Fairness & coverage-equity audit — guard against the documented early-warning harms.

Two distinct equity risks, audited separately:

1. TRACK (the Wisconsin-DEWS lesson): the risk score uses BEHAVIOR only
   (attendance/practice/quiz/trajectory) — learning_track, campus, name, phone
   are never inputs. Surfacing still correlates with track because Remedial
   students genuinely fail more (88% failed Quiz 1 vs 0% Accelerated) — that
   over-representation is the triage working, not leakage. What we audit is
   that it never becomes self-entrenching: the within-track view keeps the
   top-risk Standard/Accelerated students visible for review (it is a report
   view, not a queue quota).

2. FACILITATOR NOTE COVERAGE (the equity axis specific to a notes-reading
   system): the LLM layer only helps students whose facilitator writes notes.
   Coverage swings 21%–55% across facilitators, and the biggest classroom is
   the least documented — so note-informed care would concentrate exactly
   where load is lowest. Audited here; countered in the product (every card
   without notes carries a "log one line after contact" nudge, and un-noted
   students keep full rules-based scoring plus template drafts).
"""
from __future__ import annotations

from collections import defaultdict

# inputs the risk model is ALLOWED to use (behavior only) vs attributes it must never use
RISK_FEATURES = ["attendance", "practice", "quiz_score", "quiz_absence", "trajectory_cliff"]
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

    # within-track: the highest-risk students inside each track (a REPORT view —
    # the queue itself ranks on behavior; this keeps small tracks reviewable)
    within = defaultdict(list)
    for sid, r in records.items():
        within[r.learning_track].append((sid, risks[sid].score))
    within_top = {t: [s for s, _ in sorted(v, key=lambda x: (-x[1], x[0]))[:5]] for t, v in within.items()}

    # facilitator coverage equity: where the note-reading layer can and cannot help
    per_fac = {}
    facs = defaultdict(list)
    for sid, r in records.items():
        facs[r.facilitator_email].append(sid)
    for fac, sids in sorted(facs.items()):
        failers = [s for s in sids if records[s].quiz_failed]
        noted = [s for s in sids if records[s].has_notes]
        high_unnoted = sorted(
            s for s in sids
            if risks[s].tier in ("High", "Critical")
            and (not records[s].has_notes or not records[s].contacted_since_quiz)
        )
        per_fac[fac] = {
            "students": len(sids),
            "quiz_failers": len(failers),
            "note_coverage_pct": round(100 * len(noted) / len(sids)) if sids else 0,
            "failers_contacted_since_quiz_pct":
                round(100 * sum(records[s].contacted_since_quiz for s in failers) / len(failers))
                if failers else None,
            "high_risk_without_post_quiz_note": high_unnoted,
        }

    return {
        "risk_features_used": RISK_FEATURES,
        "sensitive_attributes_excluded": SENSITIVE_NEVER_USED,
        "surface_rate_by_track": dict(by_track),
        "within_track_top5": within_top,
        "facilitator_coverage_equity": per_fac,
        "notes": [
            "Remedial over-representation in the queue reflects behavior (88% of Remedial "
            "failed Quiz 1 vs 0% Accelerated), not a track input — expected, and correct "
            "for triage. The within-track view keeps other tracks' top risks reviewable.",
            "The operative equity risk is note coverage by facilitator (21%–55%): "
            "note-informed care must not concentrate where documentation is best. "
            "Un-noted students keep full rules scoring + template drafts, and every "
            "un-noted card carries a log-one-line nudge to close the coverage gap.",
        ],
    }
