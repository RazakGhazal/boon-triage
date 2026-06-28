"""Executable acceptance: the 12 demo students must behave as designed.

Two halves:
  - DETERMINISTIC (numbers only): trap handling + risk tier, no LLM needed.
  - FUSION (with injected note-states): the 3 decision rules, incl. the two
    bug-fixes the lean design exists to guarantee:
      * S051 (quiz-fail + cram) must NOT be demotable by a soft 'on_track' note
      * S145 (quiz-0 absence) must NEVER read as a real failing score
Runs under pytest, or directly: `python tests/test_cast.py`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.decide import decide
from src.ingest import load_records
from src.notes import NoteState
from src.risk import assess

RECS = load_records()


def _d(sid, **state):
    r = RECS[sid]
    return decide(r, assess(r), NoteState(student_id=sid, **state))


# ---- deterministic: data traps + risk tier (no LLM) ----
def test_S145_quiz0_is_absence_not_failure():
    r = RECS["S145"]
    assert r.absent_during_quiz is True
    assert r.quiz_failed is False           # the 0 is an exam-day absence
    assert assess(r).tier in ("Low", "Medium")  # NOT Critical

def test_S004_dirty_phone_survives_and_fails():
    r = RECS["S004"]
    assert r.parent_phone_flag == "missing_plus"
    assert r.parent_phone_e164.startswith("+966")
    assert r.quiz_failed is True

def test_S199_invisible_atrisk_corrupt_target_caught_by_level():
    r = RECS["S199"]
    assert r.target_corrupt is True         # target 12 < 60
    assert r.recent_cliff is False          # chronic-low, not a cliff
    assert assess(r).tier == "Critical"     # caught by LEVEL, not trajectory

def test_S023_silent_dropout_is_critical_without_llm():
    r = RECS["S023"]
    assert r.recent_cliff is True
    assert assess(r).tier == "Critical"     # deterministic — the marquee point

def test_S005_cliff_critical():
    assert RECS["S005"].recent_cliff is True
    assert assess(RECS["S005"]).tier == "Critical"

def test_S051_cram_spike_not_credited():
    r = RECS["S051"]
    assert r.practice_max_day >= 100        # the 120-question cram day exists
    assert r.practice_median < 5            # median ignores it -> not credited
    assert assess(r).tier in ("High", "Critical")

def test_S049_clean_critical_and_S076_true_negative():
    assert assess(RECS["S049"]).tier == "Critical"
    assert assess(RECS["S076"]).tier == "Low"


# ---- fusion: the 3 rules, via injected note-states ----
def test_S005_failing_note_escalates_and_calls_parent():
    a = _d("S005", state="failing", concern="urgent", confidence="high", suggested_action="call_parent")
    assert a.priority == "Critical" and a.lane == "queue"
    assert a.action_type == "call_parent"
    assert any("failing" in x for x in a.reasons)

def test_S051_working_note_CANNOT_demote_a_failing_crammer():
    a = _d("S051", state="on_track", confidence="high")   # the dangerous case
    assert a.lane == "queue"                # must stay surfaced
    assert a.priority in ("High", "Critical")  # NOT demoted to Low

def test_S145_working_note_demotes_to_left_alone():
    a = _d("S145", state="on_track", confidence="high")
    assert a.lane == "leave_alone"          # correctly off the queue

def test_S017_note_only_crisis_is_surfaced():
    a = _d("S017", state="needs_help", concern="worried", confidence="medium")
    assert a.lane == "queue"
    assert a.priority in ("Medium", "High", "Critical")  # clean numbers, surfaced by the note

def test_S013_vague_note_goes_to_human_review():
    a = _d("S013", state="needs_help", confidence="low")
    assert a.lane == "human_review"

def test_S076_positive_note_left_alone():
    a = _d("S076", state="on_track", confidence="high")
    assert a.lane == "leave_alone"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}  {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
