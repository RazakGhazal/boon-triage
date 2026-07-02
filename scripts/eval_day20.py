#!/usr/bin/env python3
"""Day-20 readout — pre-registered on Day 14 (see docs/EVAL_PLAN.md).

Runs the moment Quiz-2 data exists:
    python scripts/eval_day20.py --quiz2 data/quiz2.csv [--contact-log contact_log.csv]

quiz2.csv:       student_id,score
contact_log.csv: the CSV exported from action_queue.html ("mark contacted")

Without --quiz2 it prints the frozen plan and exits — that is intentional:
the analysis is committed before the outcomes exist.
"""
import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from src import config as C  # noqa: E402

WINDOW = [d for d in ("2025-10-11", "2025-10-12", "2025-10-13", "2025-10-14", "2025-10-15",
                      "2025-10-16", "2025-10-17", "2025-10-18", "2025-10-19")]
RD_BAND = 2  # ± queue ranks around the capacity cutoff


def _read_csv(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiz2", default=os.path.join(C.DATA_DIR, "quiz2.csv"))
    ap.add_argument("--contact-log", default=None)
    args = ap.parse_args()

    if not os.path.exists(args.quiz2):
        print("quiz2 data not found — nothing to score yet. This is the PRE-REGISTERED plan:\n")
        print(open(os.path.join(HERE, "docs", "EVAL_PLAN.md"), encoding="utf-8").read())
        return

    # --- frozen treatment assignment: the committed Day-14 queue ---
    queue = json.load(open(os.path.join(C.OUTPUT_DIR, "queue.json"), encoding="utf-8"))

    # --- who failed Quiz 1 (from raw data, same definition as the pipeline) ---
    daily = _read_csv(os.path.join(C.DATA_DIR, "student_daily_metrics.csv"))
    failers, absentees = set(), set()
    for row in daily:
        if row["date"] != C.QUIZ1_DATE or row["last_quiz_score"] in ("", None):
            continue
        score = float(row["last_quiz_score"])
        if score == 0 and row["session_attended_min"] in ("", None):
            absentees.add(row["student_id"])
        elif score < C.PASS_THRESHOLD:
            failers.add(row["student_id"])

    # --- contacts in the window: notes + exported log ---
    contacted = set()
    for n in _read_csv(os.path.join(C.DATA_DIR, "facilitator_notes.csv")):
        if n["date"] in WINDOW:
            contacted.add(n["student_id"])
    if args.contact_log and os.path.exists(args.contact_log):
        for row in _read_csv(args.contact_log):
            contacted.add(row["student_id"])

    quiz2 = {r["student_id"]: float(r["score"]) for r in _read_csv(args.quiz2) if r["score"] != ""}

    # --- PRIMARY: failer contact rate in Days 11-19 ---
    reached = failers & contacted
    primary = {"failers": len(failers), "contacted_d11_19": len(reached),
               "contact_rate_pct": round(100 * len(reached) / len(failers)) if failers else None,
               "absentees_followed_up": sorted(absentees & contacted), "absentees": sorted(absentees)}

    # --- SECONDARY: RD at the capacity cutoff (within facilitator, ±RD_BAND ranks) ---
    inside, outside = [], []
    for fac, groups in queue["facilitators"].items():
        pr = [r for r in groups.get("priority", [])]
        wl = [r for r in groups.get("messages", []) if r.get("call_waitlisted")]
        band_in = [r["student_id"] for r in pr[-RD_BAND:]]          # just inside the cutoff
        band_out = [r["student_id"] for r in wl[:RD_BAND]]          # just outside it
        inside += [quiz2[s] for s in band_in if s in quiz2]
        outside += [quiz2[s] for s in band_out if s in quiz2]
    rd = {"n_inside": len(inside), "n_outside": len(outside),
          "mean_quiz2_inside": round(sum(inside) / len(inside), 1) if inside else None,
          "mean_quiz2_outside": round(sum(outside) / len(outside), 1) if outside else None,
          "band_ranks": RD_BAND,
          "note": "local effect of a call beyond a message; directional at this n"}

    # --- GUARDRAILS: by track ---
    meta = {m["student_id"]: m for m in _read_csv(os.path.join(C.DATA_DIR, "student_metadata.csv"))}
    by_track = {}
    for sid in failers:
        t = meta[sid]["learning_track"]
        d = by_track.setdefault(t, {"failers": 0, "contacted": 0})
        d["failers"] += 1
        d["contacted"] += sid in contacted

    report = {"primary_failer_contact_rate": primary, "secondary_rd_at_cutoff": rd,
              "guardrail_contact_by_track": by_track,
              "preregistered": "docs/EVAL_PLAN.md (frozen Day 14)"}
    out = os.path.join(C.OUTPUT_DIR, "day20_report.json")
    json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nwritten -> {out}")


if __name__ == "__main__":
    main()
