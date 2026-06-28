"""Load the 3 CSVs into one canonical StudentRecord per student.

This is where every data trap is handled exactly once, so the rest of the
pipeline can trust the record:
  - join on student_id ONLY (names in notes != roster names)
  - last_quiz_score is carried-forward -> take the single value at QUIZ1_DATE
  - quiz 0 with a blank session on quiz day = ABSENCE, not a real zero (S145)
  - target_score < pass mark = corrupt -> never used as a signal (S199 cohort)
  - dirty phones (missing +, email-in-field) normalized + flagged (S004, S098)
  - blank session cells kept distinct from real 0.0 minutes
  - the recency window is computed relative to as_of_date, so trajectory/cliff
    detection works on any "today", not just the final day
"""
from __future__ import annotations

import os
import re
import statistics
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from . import config as C


# --------------------------------------------------------------------------- #
@dataclass
class StudentRecord:
    # identity / PII — NEVER sent to the LLM
    student_id: str
    student_name: str
    parent_phone_raw: str

    # de-identified metadata
    campus_id: str
    facilitator_email: str
    learning_track: str
    target_corrupt: bool          # target_score below the pass mark = garbage data
    parent_phone_e164: Optional[str]
    parent_phone_flag: str        # ok | missing_plus | email_in_phone | invalid | missing

    # attendance (A)
    attendance_baseline_min: Optional[float]
    attendance_recent_min: Optional[float]

    # practice / behavior (B) — median is spike-robust (ignores cram days)
    practice_median: float
    practice_max_day: int

    # coursework / quiz (C)
    quiz_score: Optional[int]
    quiz_taken: bool
    absent_during_quiz: bool
    quiz_failed: bool

    # trajectory (T)
    recent_cliff: bool

    # notes
    has_notes: bool
    note_text_concat: str

    # ---- the only thing the model ever sees ----
    def to_llm_payload(self) -> dict:
        return {
            "student_id": self.student_id,
            "notes": self.note_text_concat,
            "metrics": {
                "learning_track": self.learning_track,
                "attendance_recent_min": _r(self.attendance_recent_min),
                "attendance_baseline_min": _r(self.attendance_baseline_min),
                "practice_median_per_day": self.practice_median,
                "quiz_score": self.quiz_score,
                "quiz_taken": self.quiz_taken,
                "absent_during_quiz": self.absent_during_quiz,
                "quiz_failed": self.quiz_failed,
                "attendance_collapsed_recently": self.recent_cliff,
                "target_score_is_corrupt": self.target_corrupt,
            },
        }


def _r(x):
    return None if x is None else round(x, 1)


# --------------------------------------------------------------------------- #
def normalize_phone(raw: str) -> tuple[Optional[str], str]:
    """Return (e164_or_None, flag). Never raises."""
    if raw is None:
        return None, "missing"
    raw = str(raw).strip()
    if raw == "" or raw.lower() == "nan":
        return None, "missing"
    if "@" in raw or re.search(r"[a-zA-Z]", raw):  # S098: email dumped in phone column
        return None, "email_in_phone"
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+966") and len(digits) == 12:
        return raw, "ok"
    if digits.startswith("966") and len(digits) == 12:  # S004: 966501234504 -> +...
        return "+" + digits, "missing_plus"
    if len(digits) == 9 and digits.startswith("5"):
        return "+966" + digits, "missing_plus"
    return None, "invalid"


# --------------------------------------------------------------------------- #
def load_records(data_dir: str = None, as_of_date: str = None) -> dict[str, StudentRecord]:
    data_dir = data_dir or C.DATA_DIR
    as_of_date = as_of_date or C.AS_OF_DATE

    meta = pd.read_csv(os.path.join(data_dir, "student_metadata.csv"), dtype=str)
    daily = pd.read_csv(os.path.join(data_dir, "student_daily_metrics.csv"), dtype=str)
    notes = pd.read_csv(os.path.join(data_dir, "facilitator_notes.csv"), dtype=str)

    # numeric coercion that KEEPS blanks distinct from real zeros
    daily["session_attended_min"] = pd.to_numeric(daily["session_attended_min"], errors="coerce")
    daily["practice_questions"] = pd.to_numeric(daily["practice_questions"], errors="coerce")
    daily["last_quiz_score"] = pd.to_numeric(daily["last_quiz_score"], errors="coerce")

    # recency window RELATIVE to as_of_date: the last 2 active days on/before "today"
    active_sorted = [d for d in C.ACTIVE_DATES if d <= as_of_date]
    active = set(active_sorted)
    recent = set(active_sorted[-2:])
    baseline = active - recent
    daily = daily[daily["date"].isin(active)]

    # notes grouped by student_id ONLY
    notes_by_id: dict[str, list] = {}
    for _, n in notes.iterrows():
        notes_by_id.setdefault(n["student_id"], []).append(str(n["note_text"]))

    records: dict[str, StudentRecord] = {}
    for _, m in meta.iterrows():
        sid = m["student_id"]
        d = daily[daily["student_id"] == sid]

        # --- attendance (A): only non-null sessions ---
        sess = d.dropna(subset=["session_attended_min"])
        att_base = _mean_over(sess, baseline)
        att_recent = _mean_over(sess, recent)

        # --- practice (B): median is spike-robust; blanks -> 0 ---
        prac = d["practice_questions"].fillna(0).astype(int).tolist()
        practice_median = float(statistics.median(prac)) if prac else 0.0
        practice_max = int(max(prac)) if prac else 0

        # --- quiz (C): single carried-forward event; detect absence ---
        quiz_score, quiz_taken, absent, quiz_failed = _quiz(d, as_of_date)

        # --- trajectory (T): high-baseline -> near-zero collapse ---
        cliff = (
            att_base is not None and att_recent is not None
            and att_base >= C.CLIFF_BASELINE_MIN and att_recent <= C.CLIFF_RECENT_MAX
        )

        target_corrupt = _int(m.get("target_score"), 0) < C.CORRUPT_TARGET_THRESHOLD
        e164, phone_flag = normalize_phone(m.get("parent_phone"))
        nlist = notes_by_id.get(sid, [])

        records[sid] = StudentRecord(
            student_id=sid,
            student_name=m.get("student_name", ""),
            parent_phone_raw=str(m.get("parent_phone", "")),
            campus_id=m.get("campus_id", ""),
            facilitator_email=m.get("facilitator_email", ""),
            learning_track=m.get("learning_track", ""),
            target_corrupt=target_corrupt,
            parent_phone_e164=e164,
            parent_phone_flag=phone_flag,
            attendance_baseline_min=att_base,
            attendance_recent_min=att_recent,
            practice_median=practice_median,
            practice_max_day=practice_max,
            quiz_score=quiz_score,
            quiz_taken=quiz_taken,
            absent_during_quiz=absent,
            quiz_failed=quiz_failed,
            recent_cliff=cliff,
            has_notes=len(nlist) > 0,
            note_text_concat="\n".join(nlist),
        )
    return records


# --------------------------------------------------------------------------- #
def _mean_over(sess_df, dates: set) -> Optional[float]:
    sub = sess_df[sess_df["date"].isin(dates)]
    return float(sub["session_attended_min"].mean()) if len(sub) else None


def _quiz(d, as_of_date):
    """Take the quiz value at QUIZ1_DATE only (it is carried forward to later rows).
    A 0 with a blank session on quiz day means absent-during-quiz, not a real score."""
    if C.QUIZ1_DATE > as_of_date:
        return None, False, False, False
    qrow = d[d["date"] == C.QUIZ1_DATE]
    if len(qrow) == 0 or pd.isna(qrow["last_quiz_score"].iloc[0]):
        return None, False, False, False
    score = int(qrow["last_quiz_score"].iloc[0])
    session_blank = pd.isna(qrow["session_attended_min"].iloc[0])
    absent = session_blank and score == 0
    failed = (not absent) and score < C.PASS_THRESHOLD
    return score, True, absent, failed


def _int(v, default):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default
