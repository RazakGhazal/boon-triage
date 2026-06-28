"""v2 outputs: the closed-loop action layer's reports.

Reuses the v1 queue writer for the action queue (treatment arm), and adds the
three things v2 is about: a measured effectiveness report, a fairness audit, and
a data-grounded check of the note-reader against actual outcomes — plus a human
-readable v2 summary that ties them together.
"""
from __future__ import annotations

import json
import os

from . import config as C


def write(result, eff, fair, cross, holdout_ids, escalate, as_of, capacity, backend, out_dir=None):
    out = out_dir or C.OUTPUT_DIR
    os.makedirs(out, exist_ok=True)

    eff_json = {"summary": eff["summary"], "students": {sid: vars(o) for sid, o in eff["outcomes"].items()}}
    _dump(out, "effectiveness_report.json", eff_json)
    _dump(out, "fairness_report.json", fair)
    _dump(out, "llm_vs_outcome.json", cross)
    _dump(out, "run_log_v2.json", {
        "as_of_date": as_of, "backend": backend, "capacity_per_facilitator": capacity,
        "arms": {"treatment_surfaced": len(result["surfaced"]), "holdout_students": len(holdout_ids)},
        "escalate_prior_intervention_failed": escalate,
    })
    _dump(out, "v2_report.md", _report(result, eff, fair, cross, holdout_ids, escalate, as_of), raw=True)


def _dump(out, name, obj, raw=False):
    path = os.path.join(out, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(obj if raw else json.dumps(obj, ensure_ascii=False, indent=2))


def _report(result, eff, fair, cross, holdout_ids, escalate, as_of) -> str:
    s = eff["summary"]
    L = [
        f"# Boon Academy — v2 closed-loop action layer (as of {as_of})\n",
        "## 1. The 'attempted vs effective' gap — measured from the data",
        f"- {s['students_with_logged_intervention']} students had a logged facilitator intervention (a note).",
        f"- Outcome of those interventions (did engagement recover after?): {s['by_outcome']}",
        f"- **Only {s['re_engaged_pct_of_measurable']}% of measurable interventions re-engaged the student**; "
        f"{s['still_declining_pct_of_measurable']}% kept declining despite contact; "
        f"{s['logged_too_late_pct']}% were logged too late to act (final-day notes).",
        "- A logged note is *not* an effective intervention — this gap is the real story behind the 30%.\n",
        "## 2. The note-reader checked against real outcomes (data-grounded accuracy)",
        f"- Of {cross['n']} noted students where the LLM made a directional call, its read agreed with what "
        f"actually happened **{cross['agreement_pct']}%** of the time "
        f"(LLM 'working'→re-engaged, 'failing/refused'→declined).\n",
        "## 3. Closed loop: escalate where messaging already failed",
        f"- {len(escalate)} surfaced students were *already contacted and still declined* — they do NOT need "
        f"another drafted message; they need escalation beyond messaging: {escalate}\n",
        "## 4. Fairness audit",
        f"- Risk uses behavior only ({', '.join(fair['risk_features_used'])}); "
        f"never {', '.join(fair['sensitive_attributes_excluded'])}.",
        f"- Surface rate by track: " + ", ".join(
            f"{t} {d['surface_rate_pct']}%" for t, d in fair["surface_rate_by_track"].items()),
        f"- {fair['note']}\n",
        "## 5. Measurement arms",
        f"- Treatment (surfaced for intervention): {len(result['surfaced'])} students.",
        f"- Holdout (reserved, by facilitator cluster, to measure program lift): {len(holdout_ids)} students.",
    ]
    return "\n".join(L) + "\n"
