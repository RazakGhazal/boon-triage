"""Orchestrate: load -> assess (NEED) -> read notes (STATE) -> decide -> emit."""
from __future__ import annotations

from . import config as C
from .ingest import load_records
from .notes import extract_states, make_backend
from .output import build_queue, write_outputs
from .risk import assess


def run(use_llm: bool, as_of_date: str = None, capacity: int = None,
        campus: str = None, use_cache: bool = True, write: bool = True) -> dict:
    capacity = C.DEFAULT_CAPACITY if capacity is None else capacity
    as_of = as_of_date or C.AS_OF_DATE
    records = load_records(as_of_date=as_of)
    if campus:
        records = {k: v for k, v in records.items() if v.campus_id == campus}

    risks = {sid: assess(r) for sid, r in records.items()}
    backend = make_backend(use_llm)
    states = extract_states(records, backend, use_cache=use_cache)

    result = build_queue(records, risks, states, capacity, as_of)
    result["summary"]["backend"] = backend.name
    if backend.name == "gemini":
        result["summary"]["model"] = C.GEMINI_MODEL
    if write:
        write_outputs(result)
    result["backend"] = backend.name
    return result


def compute_lift(as_of_date: str = None, capacity: int = None) -> dict:
    """How much the LLM's note-reading changes the queue vs rules-only.
    Runs the decision layer with real note-states and with all-'none' states."""
    from .decide import decide
    capacity = C.DEFAULT_CAPACITY if capacity is None else capacity
    records = load_records(as_of_date=as_of_date)
    risks = {sid: assess(r) for sid, r in records.items()}

    states_on = extract_states(records, make_backend(True), use_cache=True)
    states_off = extract_states(records, make_backend(False), use_cache=False)

    noted = [sid for sid, r in records.items() if r.has_notes]
    changed, examples = [], []
    for sid in noted:
        on = decide(records[sid], risks[sid], states_on[sid])
        off = decide(records[sid], risks[sid], states_off[sid])
        if on.priority != off.priority or on.lane != off.lane:
            changed.append(sid)
            examples.append({"student_id": sid, "rules_only": f"{off.priority}/{off.lane}",
                             "with_notes": f"{on.priority}/{on.lane}", "note_state": on.note_state})
    return {"noted_students": len(noted), "changed": len(changed),
            "changed_ids": changed, "examples": examples}


# --------------------------------------------------------------------------- #
# v2: the closed-loop action layer (effectiveness + fairness + holdout + escalation)
# --------------------------------------------------------------------------- #
def _holdout_facilitators(records, fraction):
    """Hold out whole facilitators (clusters), deterministically, at least one."""
    import hashlib
    facs = sorted({r.facilitator_email for r in records.values()})
    k = max(1, round(fraction * len(facs)))
    ranked = sorted(facs, key=lambda f: int(hashlib.sha256(f.encode()).hexdigest(), 16))
    return set(ranked[:k])


def _llm_vs_outcome(states, outcomes):
    """Data-grounded check on the note-reader: among students whose engagement
    DECISIVELY moved (re-engaged or declined), did the LLM's read point the right
    way? (no_change / too-late are excluded — they're not a directional test.)"""
    rows, agree, total = [], 0, 0
    for sid, o in outcomes.items():
        if o.label not in ("re_engaged", "declined"):
            continue
        st = states.get(sid)
        if not st:
            continue
        predicted = ("re_engaged" if st.state == "on_track"
                     else "declined" if st.state in ("failing", "refused", "needs_help") else None)
        if predicted is None:  # state == 'none' makes no directional claim
            continue
        total += 1
        ok = predicted == o.label
        agree += ok
        rows.append({"student_id": sid, "llm_state": st.state, "outcome": o.label, "match": ok})
    return {"n": total, "agreement_pct": round(100 * agree / total) if total else None, "rows": rows}


def run_v2(use_llm: bool, as_of_date: str = None, capacity: int = None, use_cache: bool = True) -> dict:
    from . import effectiveness, fairness, output_v2
    capacity = C.DEFAULT_CAPACITY if capacity is None else capacity
    as_of = as_of_date or C.AS_OF_DATE

    records = load_records(as_of_date=as_of)
    holdout_facs = _holdout_facilitators(records, C.HOLDOUT_FRACTION)
    holdout_ids = {sid for sid, r in records.items() if r.facilitator_email in holdout_facs}
    treatment = {sid: r for sid, r in records.items() if sid not in holdout_ids}

    risks = {sid: assess(r) for sid, r in records.items()}
    backend = make_backend(use_llm)
    states = extract_states(records, backend, use_cache=use_cache)  # read all; effectiveness cross-tab needs them

    result = build_queue(treatment, {s: risks[s] for s in treatment},
                         {s: states[s] for s in treatment}, capacity, as_of)
    result["summary"]["backend"] = backend.name
    write_outputs(result)

    eff = effectiveness.assess(as_of_date=as_of)
    surfaced_ids = {r.student_id for r in result["surfaced"]}
    fair = fairness.audit(records, risks, surfaced_ids)
    cross = _llm_vs_outcome(states, eff["outcomes"])
    escalate = sorted(sid for sid in surfaced_ids
                      if eff["outcomes"].get(sid) and eff["outcomes"][sid].label == "declined")

    output_v2.write(result, eff, fair, cross, holdout_ids, escalate, as_of, capacity, backend.name)
    return {"queue": result["summary"], "effectiveness": eff["summary"], "llm_vs_outcome": cross,
            "fairness": fair, "holdout": len(holdout_ids), "escalate": escalate, "backend": backend.name}
