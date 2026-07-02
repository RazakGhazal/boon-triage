"""NEED: a transparent risk tier from 3 legible signals + a trajectory term.

Deliberately simple and explainable (a facilitator must understand why a
student is #1). No ML: 14 days, no labels. Each signal carries human-readable
reasons that flow straight into the action queue.

The five contributors (severity-ordered, no double counting):
  CLIFF   a strong attendant who collapsed to ~zero in the last days  (S023, S005)
  FAIL    failed Quiz 1                                               (S049, S199...)
  ABSENT  skipped Quiz 1 — never a "failure", but never silently OK:
          unexplained test avoidance is a classic disengagement flag  (S145)
  CHRONIC chronically low attendance, but never high (so not a cliff) (S199, S049)
  PRACTICE little sustained practice — median ignores cram spikes     (S051, S199)
"""
from __future__ import annotations

from dataclasses import dataclass

from . import config as C
from .ingest import StudentRecord


@dataclass
class Risk:
    tier: str           # Low | Medium | High | Critical
    score: int
    reasons: list       # human-readable flags
    signals: dict       # bool per signal, for tests / transparency


def _tier(score: int) -> str:
    for cutoff, name in C.TIER_CUTOFFS:
        if score >= cutoff:
            return name
    return "Low"


def assess(r: StudentRecord) -> Risk:
    score = 0
    reasons: list[str] = []

    cliff = r.recent_cliff
    fail = r.quiz_failed
    # chronic-low only counts when it is NOT a cliff (else we'd double-count the drop)
    chronic = (
        not cliff and r.attendance_recent_min is not None
        and r.attendance_recent_min < C.LOW_ATTENDANCE_MIN
    )
    low_practice = r.practice_median < C.LOW_PRACTICE_MEDIAN

    if cliff:
        score += 6  # a silent collapse from a strong baseline is a top-tier emergency on its own
        reasons.append(
            f"attendance collapsed from a strong baseline "
            f"({r.attendance_baseline_min:.0f} min) to near-zero in the last days "
            f"— possible silent dropout"
        )
    if fail:
        score += 3
        reasons.append(f"failed Quiz 1 (scored {r.quiz_score} < {C.PASS_THRESHOLD})")
    if r.absent_during_quiz:
        score += 2
        reasons.append(
            "missed Quiz 1 (the '0' is an exam-day absence, not a real score) — verify why"
        )
    if chronic:
        score += 2
        reasons.append(
            f"chronically low attendance (recent avg {r.attendance_recent_min:.0f} min/session)"
        )
    if low_practice:
        score += 1
        verb = "little sustained practice"
        if r.practice_max_day >= 50:  # cram: a big single-day spike the median ignores
            verb += f" (a {r.practice_max_day}-question cram day is not counted as engagement)"
        reasons.append(f"{verb} (median {r.practice_median:.0f} questions/day)")

    return Risk(
        tier=_tier(score),
        score=score,
        reasons=reasons,
        signals={"cliff": cliff, "fail": fail, "quiz_absent": r.absent_during_quiz,
                 "chronic_low_att": chronic, "low_practice": low_practice},
    )
