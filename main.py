#!/usr/bin/env python3
"""Boon Academy intervention-triage — entry point.

  python main.py                 # full run (Gemini note-reader; needs GEMINI_API_KEY in .env)
  python main.py --no-llm        # rules-only baseline (no key needed)
  python main.py --lift          # quantify what the note-reader changes vs rules-only
  python main.py --diagnose-cast # print the demo students' outcomes
"""
import argparse

from src import config as C
from src.pipeline import compute_lift, run, run_v2


def main():
    p = argparse.ArgumentParser(description="Boon Academy intervention triage")
    p.add_argument("--no-llm", action="store_true", help="rules-only baseline (no API key)")
    p.add_argument("--as-of-date", default=C.AS_OF_DATE, help="the pipeline's 'today' (default %(default)s)")
    p.add_argument("--capacity", type=int, default=C.DEFAULT_CAPACITY, help="max actionable students per facilitator")
    p.add_argument("--campus", default=None, help="restrict to one campus_id")
    p.add_argument("--lift", action="store_true", help="report the note-reader's lift vs rules-only and exit")
    p.add_argument("--v2", action="store_true", help="run the v2 closed-loop action layer (effectiveness + fairness + holdout)")
    p.add_argument("--diagnose-cast", action="store_true", help="print the demo students and exit")
    args = p.parse_args()

    if args.lift:
        rep = compute_lift(args.as_of_date, args.capacity)
        print(f"\nNote-reader lift: the notes changed the queue for "
              f"{rep['changed']} of {rep['noted_students']} noted students.")
        for e in rep["examples"]:
            print(f"  {e['student_id']}: {e['rules_only']:>18}  ->  {e['with_notes']:<18}  ({e['note_state']})")
        return

    if args.v2:
        rep = run_v2(use_llm=not args.no_llm, as_of_date=args.as_of_date, capacity=args.capacity)
        e, c = rep["effectiveness"], rep["llm_vs_outcome"]
        print(f"\nBoon Academy v2 (closed loop) — backend: {rep['backend']} · as of {args.as_of_date}")
        print(f"  attempted vs effective: of {e['students_with_logged_intervention']} logged interventions, "
              f"only {e['re_engaged_pct_of_measurable']}% re-engaged · "
              f"{e['still_declining_pct_of_measurable']}% still declining · {e['logged_too_late_pct']}% logged too late")
        print(f"  note-reader vs real outcomes: {c['agreement_pct']}% agreement (n={c['n']})")
        print(f"  escalate (prior intervention already failed): {rep['escalate']}")
        print(f"  arms: {rep['queue']['students_surfaced']} treatment-surfaced · {rep['holdout']} holdout")
        print("  outputs/ -> queue.* · effectiveness_report.json · fairness_report.json · llm_vs_outcome.json · v2_report.md")
        return

    result = run(use_llm=not args.no_llm, as_of_date=args.as_of_date,
                 capacity=args.capacity, campus=args.campus)
    s = result["summary"]
    print(f"\nBoon Academy triage — backend: {result['backend']} · as of {s['as_of_date']}")
    print(f"  {s['students_total']} students -> {s['actionable']} actionable, "
          f"{s['human_review']} human-review, {s['students_left_alone']} left alone")
    print(f"  by priority: {s['by_priority']}")
    print(f"  outputs/ -> queue.csv · queue.json · action_queue.html · run_log.json")

    if args.diagnose_cast:
        _diagnose(result)


def _diagnose(result):
    cast = ["S049", "S023", "S005", "S070", "S145", "S017", "S123", "S199", "S013", "S004", "S076", "S051"]
    rows = {r.student_id: r for r in result["surfaced"]}
    print("\nDemo cast:")
    for sid in cast:
        r = rows.get(sid)
        if r is None:
            print(f"  {sid}: left alone (not surfaced)")
        else:
            print(f"  {sid}: {r.priority:8} {r.lane:13} state={r.note_state:10} action={r.action_type}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:  # e.g. missing GEMINI_API_KEY — clean message, no traceback
        raise SystemExit(f"\n{e}")
