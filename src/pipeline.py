"""Orchestrate: load -> assess (NEED) -> read notes (STATE) -> decide -> emit."""
from __future__ import annotations

import os

from . import config as C
from .ingest import load_records
from .notes import NoteState, extract_states, make_backend
from .output import build_queue, write_outputs
from .risk import assess


def run(use_llm: bool, as_of_date: str = None, capacity: int = None,
        campus: str = None, use_cache: bool = True, write: bool = True,
        invocation: str = None, workers: int = 4) -> dict:
    capacity = C.DEFAULT_CAPACITY if capacity is None else capacity
    as_of = as_of_date or C.AS_OF_DATE
    records = load_records(as_of_date=as_of)
    if campus:
        records = {k: v for k, v in records.items() if v.campus_id == campus}

    risks = {sid: assess(r) for sid, r in records.items()}
    backend = make_backend(use_llm)
    states = extract_states(records, backend, use_cache=use_cache, workers=workers)

    result = build_queue(records, risks, states, capacity, as_of, invocation=invocation)
    result["summary"]["backend"] = backend.name
    if backend.name == "gemini":
        result["summary"]["model"] = C.GEMINI_MODEL
    if write:
        write_outputs(result)
    result["backend"] = backend.name
    return result


# --------------------------------------------------------------------------- #
def _lift_vs_rules(records, risks, states, noted) -> dict:
    """What the note-reading changed vs rules-only: run the decision layer with
    the real note-states and with all-'none' states, diff the outcomes."""
    from .decide import decide
    changed, examples, direction = [], [], {"escalated": 0, "de_escalated": 0, "review": 0}
    order = ["Low", "Medium", "High", "Critical"]
    for sid in noted:
        on = decide(records[sid], risks[sid], states[sid])
        off = decide(records[sid], risks[sid], NoteState(student_id=sid))
        if on.priority != off.priority or on.lane != off.lane:
            changed.append(sid)
            if on.lane == "human_review":
                direction["review"] += 1
            elif order.index(on.priority) > order.index(off.priority):
                direction["escalated"] += 1
            else:
                direction["de_escalated"] += 1
            examples.append({
                "student_id": sid, "quiz_failed": records[sid].quiz_failed,
                "rules_only_priority": off.priority, "rules_only_lane": off.lane,
                "with_notes_priority": on.priority, "with_notes_lane": on.lane,
                "rules_only": f"{off.priority}/{off.lane}", "with_notes": f"{on.priority}/{on.lane}",
                "note_state": on.note_state, "blocker": on.blocker,
                "summary": states[sid].summary, "evidence_ar": states[sid].evidence,
            })
    return {"noted_students": len(noted), "changed": len(changed),
            "direction": direction, "examples": examples}


def compute_lift(as_of_date: str = None, capacity: int = None, workers: int = 4) -> dict:
    records = load_records(as_of_date=as_of_date)
    risks = {sid: assess(r) for sid, r in records.items()}
    states = extract_states(records, make_backend(True), use_cache=True, workers=workers)
    noted = [sid for sid, r in records.items() if r.has_notes]
    return _lift_vs_rules(records, risks, states, noted)


# --------------------------------------------------------------------------- #
# v2: the measurement & audit layer. No holdout — denying triage to a live
# classroom is ethically wrong and statistically empty at this scale; the
# causal designs live in docs/EVAL_PLAN.md (RD at the capacity cutoff, stepped-
# wedge rollout). What v2 DOES claim is only what the data can support:
# the measured KPI baseline, a Day-9 backtest, a gold-set extractor eval,
# the notes' lift over rules-only, and honest descriptive effectiveness.
# --------------------------------------------------------------------------- #
def run_v2(use_llm: bool, as_of_date: str = None, capacity: int = None,
           use_cache: bool = True, invocation: str = None, workers: int = 4) -> dict:
    from . import backtest, effectiveness, eval_extractor, fairness, output_v2
    capacity = C.DEFAULT_CAPACITY if capacity is None else capacity
    as_of = as_of_date or C.AS_OF_DATE

    records = load_records(as_of_date=as_of)
    risks = {sid: assess(r) for sid, r in records.items()}
    backend = make_backend(use_llm)
    states = extract_states(records, backend, use_cache=use_cache, workers=workers)

    result = build_queue(records, risks, states, capacity, as_of, invocation=invocation)
    result["summary"]["backend"] = backend.name
    if backend.name == "gemini":
        result["summary"]["model"] = C.GEMINI_MODEL
    write_outputs(result)

    eff = effectiveness.assess(as_of_date=as_of)
    surfaced_ids = {r.student_id for r in result["surfaced"]}
    fair = fairness.audit(records, risks, surfaced_ids)
    escalate = sorted(sid for sid in surfaced_ids
                      if eff["outcomes"].get(sid) and eff["outcomes"][sid].label == "declined")
    bt = backtest.run_backtest()

    ext = None
    if backend.name == "gemini" and os.path.exists(eval_extractor.GOLD_PATH):
        ext = eval_extractor.evaluate(states)
        eval_extractor.write_report(ext)

    noted = [sid for sid, r in records.items() if r.has_notes]
    lift = _lift_vs_rules(records, risks, states, noted) if backend.name == "gemini" else None

    output_v2.write(result, eff, fair, ext, bt, lift, escalate, as_of, capacity, backend.name)
    return {"queue": result["summary"], "effectiveness": eff["summary"], "extractor_eval": ext,
            "backtest": bt, "lift": lift, "fairness": fair, "escalate": escalate,
            "backend": backend.name}
