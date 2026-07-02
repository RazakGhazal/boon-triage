"""v2 outputs: the measurement & audit reports.

Every number in the report is one the data can actually support: the measured
KPI baseline, a Day-9 backtest of the ranking, a gold-set eval of the
extractor, the notes' lift over rules-only, descriptive contact outcomes with
their limitations attached, and the coverage-equity audit. The causal designs
(RD at the capacity cutoff, stepped-wedge rollout) are pre-registered in
docs/EVAL_PLAN.md and run on Day 20 — not claimed early.
"""
from __future__ import annotations

import json
import os

from . import config as C


def write(result, eff, fair, ext, bt, lift, escalate, as_of, capacity, backend, out_dir=None):
    out = out_dir or C.OUTPUT_DIR
    os.makedirs(out, exist_ok=True)

    eff_json = {"summary": eff["summary"], "students": {sid: vars(o) for sid, o in eff["outcomes"].items()}}
    _dump(out, "effectiveness_report.json", eff_json)
    _dump(out, "fairness_report.json", fair)
    if lift is not None:
        _dump(out, "lift_report.json", lift)
    _dump(out, "run_log_v2.json", {
        "as_of_date": as_of, "backend": backend, "capacity_per_facilitator": capacity,
        "invocation": result["summary"].get("invocation"),
        "kpi": {k: result["summary"][k] for k in
                ("failers_total", "failers_with_action_today", "failers_contacted_since_quiz",
                 "contact_rate_pct", "days_to_next_quiz")},
        "escalate_contact_already_failing": escalate,
    })
    _dump(out, "v2_report.md", _report(result, eff, fair, ext, bt, lift, escalate, as_of), raw=True)


def _dump(out, name, obj, raw=False):
    path = os.path.join(out, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(obj if raw else json.dumps(obj, ensure_ascii=False, indent=2))


def _report(result, eff, fair, ext, bt, lift, escalate, as_of) -> str:
    s = result["summary"]
    e = eff["summary"]
    fac_rates = {f: k["failers_contacted_since_quiz_pct"]
                 for f, k in fair["facilitator_coverage_equity"].items()
                 if k["failers_contacted_since_quiz_pct"] is not None}
    lo, hi = (min(fac_rates.values()), max(fac_rates.values())) if fac_rates else (None, None)

    L = [
        f"# Boon Academy — v2 measurement & audit (as of {as_of})\n",
        "## 1. The KPI, measured from the data",
        f"- **{s['failers_total']} students failed Quiz 1.** Only **{s['failers_contacted_since_quiz']} "
        f"({s['contact_rate_pct']}%)** have any logged contact since the quiz, with "
        f"{s['days_to_next_quiz']} days left to Quiz 2 — and the per-facilitator range is "
        f"{lo}%–{hi}%. That measured gap is the problem statement, reproduced from the raw data.",
        f"- Under the two-tier queue, **{s['failers_with_action_today']}/{s['failers_total']} failers "
        f"have a ready action today** ({s['priority_actions']} calls/1-on-1s capped at "
        f"{s['capacity_per_facilitator']} per facilitator; {s['messages_today']} drafted messages, "
        f"uncapped; {s['human_review']} human-review). Messages are never capped — a fixed top-8 "
        f"list would cap facilitator8 (16 failers) at 50% coverage forever.\n",
        "## 2. Does the ranking point the right way? (Day-9 backtest)",
        f"- Scoring every student on days 1–9 only (pre-quiz clock) and checking against who "
        f"actually failed Quiz 1: **AUC {bt['auc']}**, precision@{bt['k']} = {bt['precision_at_k']}, "
        f"and {bt['failers_already_surfaced_medium_plus_pct']}% of eventual failers were already "
        f"surfaced (Medium+) the day before the quiz.",
        f"- Scope: {bt['caveats'][0]}.\n",
    ]

    L.append("## 3. Is the note-reader reading right? (gold-set eval)")
    if ext:
        g = ext["guardrails"]
        L += [
            f"- Against {ext['n_threads']} human-labeled threads (labeled from the notes only, "
            f"before this extractor version ran — eval/CODEBOOK.md): "
            f"**{ext['strict_agreement_pct']}% strict / {ext['lenient_agreement_pct']}% lenient "
            f"agreement, Cohen's κ = {ext['cohen_kappa_state']}** on the 6-state label; "
            f"blocker agreement {ext['blocker_agreement_pct']}%.",
            f"- Guardrails in operation: {g['faithfulness_gate_trips']} faithfulness-gate trips "
            f"(non-'none' state without a verbatim Arabic span), "
            f"{g['low_confidence_abstentions']} low-confidence abstentions → human-review lane.",
            f"- Remaining disagreements ({len(ext['disagreements'])}) are listed in "
            f"outputs/extractor_eval.json for qualitative review.\n",
        ]
    else:
        L.append("- (run with the LLM on to produce the gold-set eval)\n")

    L.append("## 4. What reading the notes changed (vs rules-only)")
    if lift:
        d = lift["direction"]
        L.append(f"- The notes changed the outcome for **{lift['changed']} of {lift['noted_students']} "
                 f"noted students**: {d['escalated']} escalated, {d['de_escalated']} de-escalated "
                 f"(capacity handed back), {d['review']} routed to human review.")
        for ex in lift["examples"][:5]:
            L.append(f"  - {ex['student_id']}: {ex['rules_only']} → {ex['with_notes']} "
                     f"({ex['note_state']}) — “{ex['evidence_ar']}”")
        L.append("")
    else:
        L.append("- (run with the LLM on to measure lift)\n")

    L += [
        "## 5. Contact ≠ effect (descriptive only — limitations attached)",
        f"- Of {e['students_with_logged_contact']} students with logged contact: {e['by_outcome']}. "
        f"Only {e['re_engaged_pct_of_measurable']}% of measurable threads re-engaged; "
        f"{e['logged_too_late_pct']}% were logged too late to act.",
        "- This is NOT a causal estimate — no control group, and regression to the mean "
        "(notes are written at dips) biases post-note movement. What it does show: **from "
        "current logs we cannot tell whether contact works** — which is exactly the argument "
        "for the one-field outcome log ('did it land?') in the roadmap.\n",
        "## 6. Escalate: contacted and still declining",
        f"- {len(escalate)} surfaced students were already contacted and kept declining — they need "
        f"a call/1-on-1, not another message: {escalate}\n",
        "## 7. Fairness & coverage equity",
        f"- Risk uses behavior only ({', '.join(fair['risk_features_used'])}); never "
        f"{', '.join(fair['sensitive_attributes_excluded'])}.",
        "- Surface rate by track: " + ", ".join(
            f"{t} {d['surface_rate_pct']}%" for t, d in fair["surface_rate_by_track"].items()) + ".",
        f"- {fair['notes'][0]}",
        f"- {fair['notes'][1]}",
        "- Per-facilitator coverage (students / failers / note coverage / failers contacted since quiz): "
        + "; ".join(
            f"{f.split('@')[0]} {k['students']}/{k['quiz_failers']}/{k['note_coverage_pct']}%/"
            f"{k['failers_contacted_since_quiz_pct']}%"
            for f, k in fair["facilitator_coverage_equity"].items()) + "\n",
        "## 8. What happens on Day 20 (pre-registered)",
        "- Primary: failer contact rate in days 11–19 vs the baseline in §1. Secondary: RD at the "
        "capacity cutoff (call vs message at the margin). Rollout to 100 campuses is a stepped "
        "wedge — the deployment order is the experiment. Frozen in docs/EVAL_PLAN.md; runs via "
        "`python scripts/eval_day20.py --quiz2 data/quiz2.csv`.",
    ]
    return "\n".join(L) + "\n"
