"""v2 outputs: the measurement & audit reports.

Every number in the report is one the data can actually support: the measured
KPI baseline, a Day-9 backtest of the ranking, a gold-set eval of the
extractor, the notes' lift over rules-only, descriptive contact outcomes with
their limitations attached, and the coverage-equity audit. The causal designs
(RD at the capacity cutoff, stepped-wedge rollout) are pre-registered in
docs/EVAL_PLAN.md and run on Day 20 — not claimed early.
"""
from __future__ import annotations

import html as _html_mod
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
        _dump(out, "notes_lift.html", _lift_html(lift, as_of), raw=True)
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
        f"- Are hand-set weights naive? Measured: equal weights score "
        f"{bt['weights_ablation']['equal_rule_weights_auc']} (≈ tuned — the design is "
        f"weight-insensitive), while a 5-fold-CV logistic on the raw features reaches "
        f"**{bt['weights_ablation']['cv_logistic_on_raw_features_auc']}** — the price of "
        f"binarizing signals into legible flags, paid deliberately (one label event; a "
        f"facilitator must understand why #1 is #1) and reclaimable via Quiz-2 recalibration.",
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


# --------------------------------------------------------------------------- #
# notes_lift.html — the with-vs-without exhibit: same students, same numbers;
# the ONLY difference between the two columns is the LLM reading the Arabic
# notes. This is the page that shows why the LLM earns its place.
# --------------------------------------------------------------------------- #
_PRI_COLOR = {"Critical": "#e23b30", "High": "#cf5e1f", "Medium": "#a37d12", "Low": "#0e9b6b"}


def _esc(x):
    return _html_mod.escape(str(x))


def _verdict(pri, lane):
    c = _PRI_COLOR.get(pri, "#697a92")
    lane_txt = {"queue": "on the queue", "leave_alone": "left alone",
                "human_review": "human review"}.get(lane, lane)
    return (f'<span class="verdict"><b style="color:{c}">{_esc(pri)}</b>'
            f'<i>{_esc(lane_txt)}</i></span>')


def _lift_html(lift, as_of) -> str:
    d = lift["direction"]
    groups = {"escalated": [], "de_escalated": [], "review": []}
    order = ["Low", "Medium", "High", "Critical"]
    for ex in lift["examples"]:
        if ex["with_notes_lane"] == "human_review":
            groups["review"].append(ex)
        elif order.index(ex["with_notes_priority"]) > order.index(ex["rules_only_priority"]):
            groups["escalated"].append(ex)
        else:
            groups["de_escalated"].append(ex)

    head = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Boon Academy — What reading the notes changed</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{{--navy:#172740;--ink:#1b2a44;--mut:#697a92;--faint:#9aa7ba;--bg:#f7f8fa;--line:#e7eaf0;
--mint:#17e4a1;--mintd:#0e9b6b;--mintbg:#eafaf3}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:"IBM Plex Sans Arabic",-apple-system,Segoe UI,Roboto,sans-serif;
background:var(--bg);color:var(--ink);font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}}
.hero{{background:var(--navy);color:#fff;padding:34px 0 30px}}
.wrap{{max-width:940px;margin:0 auto;padding:0 28px}}
.brand{{font-size:21px;font-weight:700}} .brand i{{color:var(--mint);font-style:normal}}
.brand b{{font-weight:500;color:rgba(255,255,255,.6)}}
.hero h1{{margin:16px 0 4px;font-size:30px;font-weight:700;letter-spacing:-.6px}}
.hero .sub{{margin:0;color:rgba(255,255,255,.62);font-size:14px;max-width:72ch}}
.stats{{display:flex;flex-wrap:wrap;gap:38px;margin-top:24px}}
.stats .n{{font-size:30px;font-weight:700;line-height:1;color:var(--mint)}}
.stats .l{{font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:rgba(255,255,255,.5);margin-top:4px}}
main{{padding:14px 0 64px}}
h2{{font-size:13px;letter-spacing:.07em;text-transform:uppercase;color:var(--navy);margin:38px 0 2px}}
h2 span{{color:var(--faint);font-weight:500;text-transform:none;letter-spacing:0;margin-inline-start:8px}}
.card{{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px 20px;margin-top:12px;
box-shadow:0 1px 2px rgba(20,40,80,.04)}}
.r1{{display:flex;align-items:center;gap:12px;flex-wrap:wrap}}
.sid{{font-weight:700;font-size:17px;color:var(--navy)}}
.tag{{font-size:11.5px;color:var(--mintd);border:1px solid #bdeede;border-radius:100px;padding:1px 10px;background:var(--mintbg)}}
.tag.f{{color:#e23b30;border-color:#f5c6c0;background:#fdecea}}
.verdict{{display:inline-flex;flex-direction:column;line-height:1.25;padding:5px 13px;border:1px solid var(--line);
border-radius:10px;background:#fbfcfe;min-width:118px}}
.verdict b{{font-size:13px;font-weight:700;letter-spacing:.03em;text-transform:uppercase}}
.verdict i{{font-style:normal;font-size:11px;color:var(--faint)}}
.arrow{{font-size:19px;color:var(--mintd);font-weight:700}}
.lbl{{font-size:9.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--faint);margin-bottom:3px}}
.cols{{display:flex;align-items:center;gap:14px;margin-inline-start:auto;flex-wrap:wrap}}
.col{{display:flex;flex-direction:column}}
.story{{margin:11px 0 0;font-size:14px;color:#33415c}}
.ev{{direction:rtl;text-align:right;color:#0c6e4d;font-size:14px;background:var(--mintbg);
border:1px solid #d6f2e6;border-radius:10px;padding:9px 13px;margin-top:10px}}
footer{{margin-top:46px;border-top:1px solid var(--line);padding-top:16px;font-size:12px;color:var(--faint)}}
</style></head><body>
<header class="hero"><div class="wrap">
<div class="brand">bo<i>o</i>n <b>academy</b></div>
<h1>What reading the notes changed</h1>
<p class="sub">Same students, same numbers, same rules — the ONLY difference between the two verdicts on each row
is the LLM reading the facilitator's Arabic notes. Generated from the committed run of {as_of}.</p>
<div class="stats">
<div><div class="n">{lift['changed']}/{lift['noted_students']}</div><div class="l">noted students changed</div></div>
<div><div class="n" style="color:#ff8d84">{d['escalated']}</div><div class="l">escalated — crises the numbers missed</div></div>
<div><div class="n">{d['de_escalated']}</div><div class="l">de-escalated — call slots handed back</div></div>
<div><div class="n" style="color:#b7a4f4">{d['review']}</div><div class="l">to human review</div></div>
</div></div></header>
<main><div class="wrap">"""

    sections = [
        ("escalated", "Escalated", "the numbers under-called these — the note is the only early warning"),
        ("de_escalated", "De-escalated", "the numbers over-called these — the cause is known and managed; capacity goes back"),
        ("review", "Sent to a human", "the note matters but the read is uncertain — never auto-acted"),
    ]
    parts = [head]
    for key, title, sub in sections:
        if not groups[key]:
            continue
        parts.append(f"<h2>{title}<span>{_esc(sub)}</span></h2>")
        for ex in groups[key]:
            failer = '<span class="tag f">failed Quiz 1</span>' if ex["quiz_failed"] else ""
            state = f'<span class="tag">{_esc(ex["note_state"])}</span>'
            blocker = (f'<span class="tag">blocker: {_esc(ex["blocker"])}</span>'
                       if ex.get("blocker") and ex["blocker"] != "unknown" else "")
            ev = f'<div class="ev">“{_esc(ex["evidence_ar"])}”</div>' if ex.get("evidence_ar") else ""
            summary = f'<p class="story">{_esc(ex["summary"])}</p>' if ex.get("summary") else ""
            parts.append(f"""<article class="card"><div class="r1">
<span class="sid">{_esc(ex['student_id'])}</span>{failer}{state}{blocker}
<span class="cols"><span class="col"><span class="lbl">numbers only</span>{_verdict(ex['rules_only_priority'], ex['rules_only_lane'])}</span>
<span class="arrow">→</span>
<span class="col"><span class="lbl">with the notes</span>{_verdict(ex['with_notes_priority'], ex['with_notes_lane'])}</span></span>
</div>{summary}{ev}</article>""")
    parts.append('<footer>Boon Academy · rules score the numbers · the LLM reads the Arabic · '
                 'fusion decides · every claim quotes a verbatim span from a real note.</footer>')
    parts.append("</div></main></body></html>")
    return "".join(parts)
