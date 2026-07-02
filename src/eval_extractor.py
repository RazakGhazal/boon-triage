"""Extractor eval: the note-reader measured against human gold labels.

This is the ONLY supervised evaluation this dataset can support today — there
are no Quiz-2 outcomes to validate a risk ranking against, but extraction
fidelity ("does the model read the Arabic the way a careful human does?") is
measurable right now. Gold labels live in eval/gold_labels.csv and were drafted
from the notes alone (no metrics), before the v3 extractor ran — see
eval/CODEBOOK.md for the labeling rules and the ambiguity policy.

Reports: strict + lenient agreement, Cohen's kappa, per-state precision/recall,
a confusion table, blocker agreement, and the guardrail operating stats
(faithfulness-gate trips, low-confidence abstentions).
"""
from __future__ import annotations

import csv
import json
import os
from collections import Counter, defaultdict

from . import config as C

GOLD_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "eval", "gold_labels.csv")
STATES = ["none", "improving", "explained", "needs_help", "failing", "refused"]


def load_gold(path: str = GOLD_PATH) -> dict[str, dict]:
    with open(path, encoding="utf-8") as fh:
        return {row["student_id"]: row for row in csv.DictReader(fh)}


def _kappa(pairs: list[tuple[str, str]]) -> float:
    n = len(pairs)
    po = sum(1 for g, p in pairs if g == p) / n
    gold_m = Counter(g for g, _ in pairs)
    pred_m = Counter(p for _, p in pairs)
    pe = sum((gold_m[s] / n) * (pred_m[s] / n) for s in set(gold_m) | set(pred_m))
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def evaluate(states: dict, gold_path: str = GOLD_PATH) -> dict:
    """states: {student_id: NoteState} from the extractor (noted students only used)."""
    gold = load_gold(gold_path)
    pairs, blk_pairs, mism = [], [], []
    lenient_ok = 0
    conf = defaultdict(Counter)   # gold -> pred counts
    gate_trips = abstentions = 0

    for sid, g in gold.items():
        ns = states.get(sid)
        if ns is None or not getattr(ns, "state", None):
            continue
        pred = ns.state
        pairs.append((g["gold_state"], pred))
        blk_pairs.append((g["gold_blocker"], getattr(ns, "blocker", "unknown")))
        conf[g["gold_state"]][pred] += 1
        ok_strict = pred == g["gold_state"]
        ok_lenient = ok_strict or (g["ambiguous"] == "yes" and pred == g["alt_state"])
        lenient_ok += ok_lenient
        if not ok_lenient:
            mism.append({"student_id": sid, "gold": g["gold_state"], "pred": pred,
                         "confidence": ns.confidence, "rationale": g["rationale"]})
        if not getattr(ns, "faithful", True):
            gate_trips += 1
        if ns.confidence == "low":
            abstentions += 1

    n = len(pairs)
    strict = sum(1 for g, p in pairs if g == p)
    per_state = {}
    for s in STATES:
        tp = conf[s][s]
        gold_n = sum(conf[s].values())
        pred_n = sum(conf[g][s] for g in conf)
        per_state[s] = {
            "gold_n": gold_n,
            "precision": round(tp / pred_n, 2) if pred_n else None,
            "recall": round(tp / gold_n, 2) if gold_n else None,
        }

    return {
        "n_threads": n,
        "strict_agreement_pct": round(100 * strict / n) if n else None,
        "lenient_agreement_pct": round(100 * lenient_ok / n) if n else None,  # counts codebook-flagged alt reads
        "cohen_kappa_state": round(_kappa(pairs), 2) if n else None,
        "blocker_agreement_pct": round(100 * sum(1 for g, p in blk_pairs if g == p) / n) if n else None,
        "per_state": per_state,
        "confusion_gold_to_pred": {g: dict(c) for g, c in conf.items()},
        "guardrails": {
            "faithfulness_gate_trips": gate_trips,   # non-'none' state without a verbatim span
            "low_confidence_abstentions": abstentions,  # routed to the human-review lane
        },
        "disagreements": mism,
        "provenance": "gold labels drafted from notes only, before the v3 extractor ran (eval/CODEBOOK.md)",
    }


def write_report(report: dict, out_dir: str = None) -> str:
    out_dir = out_dir or C.OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "extractor_eval.json")
    json.dump(report, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return path
