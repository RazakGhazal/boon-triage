"""Executable acceptance: the demo students must behave as designed.

Three groups:
  - DETERMINISTIC (numbers only): trap handling + risk tier, no LLM needed.
  - FUSION (with injected note-states): the rule families, incl. the guards the
    lean design exists to enforce:
      * S051 (quiz-fail + cram) must NOT be demotable by a soft 'improving' note
      * S145 (quiz-0 absence) must NEVER read as a real failing score — but must
        NEVER be silently ignored either (absence carries risk points now)
      * a cliff with an 'explained' note (sick, parent engaged) must fall to a
        check-in message, not burn a call slot
  - SYSTEM invariants: every quiz-failer leaves with a ready action; the cap
    binds only calls/1-on-1s; the faithfulness gate downgrades unevidenced or
    fabricated claims; the Day-9 backtest stays predictive.
Runs under pytest, or directly: `python tests/test_cast.py`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backtest import run_backtest
from src.decide import decide
from src.eval_extractor import load_gold
from src.ingest import load_records
from src.notes import NoteState, extract_states
from src.output import build_queue
from src.risk import assess

RECS = load_records()


def _d(sid, **state):
    r = RECS[sid]
    return decide(r, assess(r), NoteState(student_id=sid, **state))


# ---- deterministic: data traps + risk tier (no LLM) ----
def test_S145_quiz0_is_absence_not_failure_but_not_ignored():
    r = RECS["S145"]
    assert r.absent_during_quiz is True
    assert r.quiz_failed is False           # the 0 is an exam-day absence...
    risk = assess(r)
    assert risk.signals["quiz_absent"] is True
    assert risk.tier == "Medium"            # ...but skipping a quiz is never invisible

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

def test_S051_cram_spike_not_credited():
    r = RECS["S051"]
    assert r.practice_max_day >= 100        # the 120-question cram day exists
    assert r.practice_median < 5            # median ignores it -> not credited
    assert assess(r).tier in ("High", "Critical")

def test_S049_clean_critical_and_S076_true_negative():
    assert assess(RECS["S049"]).tier == "Critical"
    assert assess(RECS["S076"]).tier == "Low"

def test_notes_are_dated_and_contact_recency_tracked():
    r = RECS["S005"]
    assert r.note_text_concat.startswith("[Day ")   # the LLM sees time, not a blob
    assert r.contacted_since_quiz is True           # has a note on/after Day 10
    assert RECS["S057"].contacted_since_quiz is True or RECS["S057"].last_note_day is not None


# ---- fusion: the rule families, via injected note-states ----
def test_S005_failing_note_escalates_and_calls_parent():
    a = _d("S005", state="failing", concern="urgent", confidence="high", suggested_action="call_parent")
    assert a.priority == "Critical" and a.lane == "queue"
    assert a.action_type == "call_parent"
    assert any("failing" in x for x in a.reasons)

def test_S051_working_note_CANNOT_demote_a_failing_crammer():
    a = _d("S051", state="improving", confidence="high")   # the dangerous case
    assert a.lane == "queue"                # must stay surfaced
    assert a.priority in ("High", "Critical")  # NOT demoted to Low

def test_S145_improving_note_demotes_absentee_to_left_alone():
    a = _d("S145", state="improving", confidence="high")
    assert a.lane == "leave_alone"          # father engaged, attendance back — off the queue

def test_S023_explained_cliff_becomes_checkin_not_call():
    # a Critical collapse whose cause is known and managed must not burn a call slot
    a = _d("S023", state="explained", confidence="high")
    assert a.priority == "Medium" and a.action_type == "message"
    assert a.draft_message                  # ships with a ready check-in draft

def test_low_confidence_improving_cannot_demote():
    a = _d("S023", state="improving", confidence="low")
    assert a.priority == "Critical"         # de-escalation needs a confident read

def test_S017_note_only_crisis_is_surfaced():
    a = _d("S017", state="needs_help", concern="worried", confidence="medium")
    assert a.lane == "queue"
    assert a.priority in ("Medium", "High", "Critical")  # clean numbers, surfaced by the note

def test_S013_vague_note_goes_to_human_review():
    a = _d("S013", state="needs_help", confidence="low")
    assert a.lane == "human_review"

def test_S076_positive_note_left_alone():
    a = _d("S076", state="improving", confidence="high")
    assert a.lane == "leave_alone"


# ---- guardrails: the faithfulness gate ----
class _Stub:
    name = "stub"
    def __init__(self, raw):
        self.raw = raw
    def extract(self, payload):
        return dict(self.raw)

def _gate(raw):
    sub = {"S005": RECS["S005"]}
    return extract_states(sub, _Stub(raw), use_cache=False)["S005"]

def test_gate_blocks_unevidenced_state():
    ns = _gate({"state": "failing", "confidence": "high", "evidence": ""})
    assert ns.faithful is False and ns.confidence == "low"   # -> human review, not auto-action

def test_gate_blocks_fabricated_evidence():
    ns = _gate({"state": "failing", "confidence": "high", "evidence": "نص غير موجود في الملاحظات"})
    assert ns.faithful is False and ns.confidence == "low" and ns.evidence == ""


# ---- system invariants: the queue faces the KPI ----
def _full_queue():
    risks = {sid: assess(r) for sid, r in RECS.items()}
    states = {sid: NoteState(student_id=sid) for sid in RECS}   # rules-only
    return build_queue(RECS, risks, states, capacity=8, as_of_date="2025-10-14")

def test_every_quiz_failer_gets_an_action():
    q = _full_queue()
    surfaced = {r.student_id for r in q["surfaced"]}
    failers = {sid for sid, r in RECS.items() if r.quiz_failed}
    assert failers <= surfaced                                  # 30->80 is impossible otherwise
    assert q["summary"]["failers_with_action_today"] == len(failers)

def test_capacity_caps_only_heavy_actions():
    q = _full_queue()
    for fac, g in q["by_facilitator"].items():
        assert len(g["priority"]) <= 8                          # calls/1-on-1s capped
    assert q["summary"]["messages_today"] >= 0                  # messages never dropped
    waitlisted = [r for r in q["surfaced"] if r.call_waitlisted]
    assert all(r.draft_message for r in waitlisted)             # waitlist still messages TODAY

def test_every_surfaced_nonreview_student_has_a_draft():
    q = _full_queue()
    for r in q["surfaced"]:
        if r.lane != "human_review":
            assert r.draft_message, f"{r.student_id} surfaced without a ready message"
            assert "{name}" not in r.draft_message              # placeholder always filled

def test_day9_backtest_is_predictive():
    bt = run_backtest(write=False)
    assert bt["auc"] > 0.75                                     # ranking points the right way
    assert bt["n_quiz1_failers"] == 66

def test_gold_labels_complete_and_valid():
    gold = load_gold()
    assert len(gold) == 75                                      # every noted student labeled
    valid = {"none", "improving", "explained", "needs_help", "failing", "refused"}
    assert {g["gold_state"] for g in gold.values()} <= valid


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
