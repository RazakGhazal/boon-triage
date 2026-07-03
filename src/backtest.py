"""Day-9 backtest: the one label-supervised validation the data allows.

The risk score is a hand-set heuristic — with no Quiz-2 labels it cannot be
validated forward. But it CAN be validated backward: score every student using
ONLY days 1-9 (the quiz term is structurally absent — Quiz 1 hasn't happened
yet on that clock), then check whether that pre-quiz ranking predicts who
actually failed Quiz 1 the next day. The pipeline's as_of clock makes this a
two-line time machine: load_records(as_of_date=DAY9) is guaranteed look-ahead
free by the same clamps the production path uses.

Honest scope: this validates the behavior terms (attendance / practice / cliff)
on one quiz with n=200. It says the ranking points the right way — not that the
weights are optimal. No sklearn: AUC is Mann-Whitney with tie-averaged ranks.

It also runs the "are hand-set weights naive?" ablation, because the question
deserves a number, not a shrug: equal weights score the same as the tuned ones
(the design is weight-INsensitive), while a cross-validated logistic regression
on the raw features does beat the rules — the measured price of binarizing
continuous signals into legible flags. We pay it deliberately: one label event,
a hard legibility requirement (a facilitator must understand why #1 is #1), and
robustness to distribution shift across 100 campuses. The gap is what Quiz-2
recalibration can reclaim later.
"""
from __future__ import annotations

import json
import os

from . import config as C
from .ingest import load_records
from .risk import assess

DAY9 = "2025-10-09"   # the eve of Quiz 1 on the case clock


def _auc(scored: list[tuple[float, bool]]) -> float:
    """Mann-Whitney AUC with average ranks for ties."""
    n_pos = sum(1 for _, y in scored if y)
    n_neg = len(scored) - n_pos
    if not n_pos or not n_neg:
        return float("nan")
    by_score = sorted(scored, key=lambda t: t[0])
    ranks, i = {}, 0
    while i < len(by_score):
        j = i
        while j < len(by_score) and by_score[j][0] == by_score[i][0]:
            j += 1
        avg = (i + 1 + j) / 2  # average of ranks i+1 .. j
        for k in range(i, j):
            ranks[k] = avg
        i = j
    r_pos = sum(ranks[k] for k, (_, y) in enumerate(by_score) if y)
    return (r_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def run_backtest(as_of: str = DAY9, write: bool = True) -> dict:
    pre = load_records(as_of_date=as_of)          # what we'd have known on Day 9
    full = load_records()                          # Day-14 truth: who failed Quiz 1
    risks = {sid: assess(r) for sid, r in pre.items()}
    labels = {sid: full[sid].quiz_failed for sid in pre}  # exam-day absentee is NOT a failer

    scored = [(risks[sid].score, labels[sid]) for sid in pre]
    n_fail = sum(labels.values())
    auc = _auc(scored)

    # precision@k with k = the number of eventual failers (deterministic tie-break)
    top_k = sorted(pre, key=lambda sid: (-risks[sid].score, sid))[:n_fail]
    p_at_k = sum(labels[sid] for sid in top_k) / n_fail if n_fail else float("nan")

    flagged = {sid for sid in pre if risks[sid].tier in ("High", "Critical")}
    med_up = {sid for sid in pre if risks[sid].tier != "Low"}
    ablation = _weights_ablation(pre, risks, labels)
    report = {
        "as_of": as_of,
        "design": "score on days 1-9 only (pre-quiz clock; quiz term structurally absent), "
                  "label = failed Quiz 1 on Day 10",
        "n_students": len(pre),
        "n_quiz1_failers": n_fail,
        "auc": round(auc, 3),
        "precision_at_k": round(p_at_k, 2),
        "k": n_fail,
        "failers_already_flagged_high_or_critical_pct":
            round(100 * sum(1 for sid in flagged if labels[sid]) / n_fail) if n_fail else None,
        "failers_already_surfaced_medium_plus_pct":
            round(100 * sum(1 for sid in med_up if labels[sid]) / n_fail) if n_fail else None,
        "weights_ablation": ablation,
        "caveats": [
            "validates the behavior terms only (attendance/practice/cliff); the quiz term "
            "cannot be backtested against the same quiz",
            "one quiz, n=200 — directional, not a calibration",
            "once the queue drives interventions, forward validation against Quiz 2 is "
            "post-treatment (see docs/EVAL_PLAN.md for the RD design that handles this)",
        ],
    }
    if write:
        os.makedirs(C.OUTPUT_DIR, exist_ok=True)
        json.dump(report, open(os.path.join(C.OUTPUT_DIR, "backtest_day9.json"), "w",
                               encoding="utf-8"), ensure_ascii=False, indent=2)
    return report


def _weights_ablation(pre, risks, labels) -> dict:
    """Rules-vs-learned, quantified (numpy ships with pandas; fixed seed = reproducible)."""
    import numpy as np

    sids = sorted(pre)
    y = np.array([labels[s] for s in sids], float)

    def auc(v):
        return round(_auc(list(zip(v.tolist(), (y == 1).tolist()))), 3)

    sig = {k: np.array([risks[s].signals[k] for s in sids], float)
           for k in ("cliff", "chronic_low_att", "low_practice")}
    att_r = np.array([pre[s].attendance_recent_min or 0 for s in sids], float)
    att_b = np.array([pre[s].attendance_baseline_min or 0 for s in sids], float)
    prac_m = np.array([pre[s].practice_median for s in sids], float)
    prac_x = np.array([pre[s].practice_max_day for s in sids], float)

    # 5-fold CV logistic regression on the RAW features (plain gradient descent)
    X = np.column_stack([att_r, att_b, prac_m, prac_x, sig["cliff"],
                         sig["chronic_low_att"], sig["low_practice"]])
    X = (X - X.mean(0)) / (X.std(0) + 1e-9)
    X = np.column_stack([np.ones(len(X)), X])
    idx = np.random.RandomState(0).permutation(len(y))
    oof = np.zeros(len(y))
    for fold in np.array_split(idx, 5):
        tr = np.setdiff1d(idx, fold)
        w = np.zeros(X.shape[1])
        for _ in range(3000):
            p = 1 / (1 + np.exp(-X[tr] @ w))
            w -= 0.1 * (X[tr].T @ (p - y[tr]) / len(tr) + 0.01 * np.r_[0, w[1:]])
        oof[fold] = X[fold] @ w

    return {
        "tuned_rule_weights_auc": auc(np.array([risks[s].score for s in sids], float)),
        "equal_rule_weights_auc": auc(sig["cliff"] + sig["chronic_low_att"] + sig["low_practice"]),
        "raw_practice_median_alone_auc": auc(-prac_m),
        "cv_logistic_on_raw_features_auc": auc(oof),
        "reading": "weights barely matter (tuned≈equal); binarization is the real cost — a "
                   "learned ranker beats the rules, a gap paid deliberately for legibility "
                   "and shift-robustness, reclaimable via Quiz-2 recalibration",
    }
