"""Retrospective look at logged contacts — DESCRIPTIVE, not causal.

Every facilitator note is a dated contact; we look at what the student's
engagement did afterward and label each thread re-engaged / no-change /
declined / logged-too-late. What this supports: "from current logs we cannot
even tell whether contact works" — the argument for the one-field outcome log.

What it does NOT support: any causal claim about contact effectiveness. Named
limitations, reported alongside the numbers:
  - no control group (the 125 un-noted students are never measured)
  - regression to the mean: notes are written at dips, and dips revert — the
    post-note movement would look positive even if contact did nothing
  - "first note = the intervention" is a proxy: some notes are observations,
    58/75 threads have several notes, and an early first note leaves a
    days-thin pre-window
  - the post window is the last 2 active days — one absence swings the label

Pure data; no LLM. Independent of risk/notes so it can be audited on its own.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from . import config as C


@dataclass
class Outcome:
    student_id: str
    first_note_date: str
    n_notes: int
    att_baseline: Optional[float]   # engagement before the first intervention
    att_recent: Optional[float]     # engagement in the last 2 active days (where they ended up)
    prac_baseline: float
    prac_recent: float
    label: str  # re_engaged | no_change | declined | logged_too_late


# thresholds for the re-engagement surrogate — SYMMETRIC on purpose: an easier
# bar for "re-engaged" than for "declined" would put a thumb on the scale
_ATT_RISE, _ATT_DROP = 10.0, 10.0    # minutes/session change that counts as a real move
_PRAC_RISE, _PRAC_DROP = 4.0, 4.0    # questions/day change


def _coerce(daily: pd.DataFrame) -> pd.DataFrame:
    daily["session_attended_min"] = pd.to_numeric(daily["session_attended_min"], errors="coerce")
    daily["practice_questions"] = pd.to_numeric(daily["practice_questions"], errors="coerce")
    return daily


def assess(data_dir: str = None, as_of_date: str = None) -> dict:
    data_dir = data_dir or C.DATA_DIR
    as_of = as_of_date or C.AS_OF_DATE
    daily = _coerce(pd.read_csv(os.path.join(data_dir, "student_daily_metrics.csv"), dtype={"student_id": str, "date": str}))
    notes = pd.read_csv(os.path.join(data_dir, "facilitator_notes.csv"), dtype=str)

    active = [d for d in C.ACTIVE_DATES if d <= as_of]
    recent = [d for d in C.RECENT_DATES if d <= as_of]
    second_last = active[-2] if len(active) >= 2 else active[-1]

    outcomes: dict[str, Outcome] = {}
    for sid, g in notes.groupby("student_id"):
        ndates = sorted(d for d in g["date"] if d <= as_of)  # notes happen any day (incl. weekends)
        if not ndates:
            continue
        first = ndates[0]
        d = daily[daily["student_id"] == sid]

        # the intervention is "logged too late to act" if the first contact is on/after the last day
        if first >= second_last:
            outcomes[sid] = Outcome(sid, first, len(ndates), None, None, 0, 0, "logged_too_late")
            continue

        pre = [x for x in active if x < first]
        att_base = _mean(d, pre, "session_attended_min")
        att_rec = _mean(d, recent, "session_attended_min")
        prac_base = _mean(d, pre, "practice_questions", fill0=True) or 0.0
        prac_rec = _mean(d, recent, "practice_questions", fill0=True) or 0.0

        outcomes[sid] = Outcome(
            sid, first, len(ndates), att_base, att_rec, prac_base, prac_rec,
            _label(att_base, att_rec, prac_base, prac_rec),
        )

    return {"outcomes": outcomes, "summary": _summarize(outcomes)}


def _mean(d, dates, col, fill0=False):
    sub = d[d["date"].isin(dates)][col]
    if fill0:
        sub = sub.fillna(0)
    else:
        sub = sub.dropna()
    return float(sub.mean()) if len(sub) else None


def _label(att_b, att_r, prac_b, prac_r) -> str:
    # collapsed to near-zero attendance from a real baseline = clear decline (intervention failed)
    if att_b is not None and att_r is not None:
        if att_r <= 10 and att_b >= 30:
            return "declined"
        if att_r - att_b >= _ATT_RISE or prac_r - prac_b >= _PRAC_RISE:
            return "re_engaged"
        if att_b - att_r >= _ATT_DROP or prac_b - prac_r >= _PRAC_DROP:
            return "declined"
        return "no_change"
    # attendance unknown — fall back to practice
    if prac_r - prac_b >= _PRAC_RISE:
        return "re_engaged"
    if prac_b - prac_r >= _PRAC_DROP:
        return "declined"
    return "no_change"


def _summarize(outcomes: dict) -> dict:
    from collections import Counter
    c = Counter(o.label for o in outcomes.values())
    n = len(outcomes) or 1
    measurable = sum(v for k, v in c.items() if k != "logged_too_late") or 1
    return {
        "students_with_logged_contact": len(outcomes),
        "by_outcome": dict(c),
        "logged_too_late_pct": round(100 * c.get("logged_too_late", 0) / n),
        "re_engaged_pct_of_measurable": round(100 * c.get("re_engaged", 0) / measurable),
        "still_declining_pct_of_measurable": round(100 * c.get("declined", 0) / measurable),
        "caveats": [
            "descriptive only — no control group; the 125 un-noted students are never measured",
            "regression to the mean: notes are written at dips, and dips revert",
            "'first note = intervention' is a proxy; many notes are observations",
        ],
    }
