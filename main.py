#!/usr/bin/env python3
"""Boon Academy intervention-triage — entry point.

  python main.py                 # action queue (Gemini note-reader; needs GEMINI_API_KEY in .env)
  python main.py --v2            # queue + full measurement layer (backtest, gold-set eval, lift, audits)
  python main.py --no-llm        # rules-only baseline (no key needed)
  python main.py --lift          # quantify what the note-reader changes vs rules-only
  python main.py --backtest      # Day-9 ranking backtest vs Quiz-1 outcomes (no LLM)
  python main.py --eval-extractor# note-reader vs the human gold labels (uses cache)
  python main.py --diagnose-cast # print the demo students' outcomes
"""
import argparse
import sys

from src import config as C
from src.pipeline import compute_lift, run, run_v2

INVOCATION = "python " + " ".join(sys.argv)


def main():
    p = argparse.ArgumentParser(description="Boon Academy intervention triage")
    p.add_argument("--no-llm", action="store_true", help="rules-only baseline (no API key)")
    p.add_argument("--as-of-date", default=C.AS_OF_DATE, help="the pipeline's 'today' (default %(default)s)")
    p.add_argument("--capacity", type=int, default=C.DEFAULT_CAPACITY,
                   help="max calls/1-on-1s per facilitator (messages are never capped)")
    p.add_argument("--campus", default=None, help="restrict to one campus_id")
    p.add_argument("--workers", type=int, default=4,
                   help="parallel note-reader calls (1 = ordered one-by-one stream for demos)")
    p.add_argument("--lift", action="store_true", help="report the note-reader's lift vs rules-only and exit")
    p.add_argument("--backtest", action="store_true", help="Day-9 ranking backtest vs Quiz-1 outcomes and exit")
    p.add_argument("--eval-extractor", action="store_true", help="gold-set eval of the note-reader and exit")
    p.add_argument("--v2", action="store_true", help="queue + the full measurement & audit layer")
    p.add_argument("--diagnose-cast", action="store_true", help="print the demo students and exit")
    args = p.parse_args()

    if args.backtest:
        from src.backtest import run_backtest
        bt = run_backtest()
        print("\nDay-9 backtest (score on days 1-9, label = failed Quiz 1 on Day 10):")
        print(f"  AUC {bt['auc']} · precision@{bt['k']} {bt['precision_at_k']} · "
              f"{bt['failers_already_surfaced_medium_plus_pct']}% of failers already Medium+ pre-quiz")
        print("  -> outputs/backtest_day9.json")
        return

    if args.eval_extractor:
        from src.eval_extractor import evaluate, write_report
        from src.ingest import load_records
        from src.notes import extract_states, make_backend
        records = load_records(as_of_date=args.as_of_date)
        states = extract_states(records, make_backend(True), use_cache=True, workers=args.workers)
        rep = evaluate(states)
        path = write_report(rep)
        print(f"\nExtractor vs {rep['n_threads']} gold-labeled threads: "
              f"{rep['strict_agreement_pct']}% strict / {rep['lenient_agreement_pct']}% lenient, "
              f"kappa {rep['cohen_kappa_state']} · blocker {rep['blocker_agreement_pct']}%")
        print(f"  gate trips {rep['guardrails']['faithfulness_gate_trips']} · "
              f"abstentions {rep['guardrails']['low_confidence_abstentions']} · -> {path}")
        return

    if args.lift:
        rep = compute_lift(args.as_of_date, args.capacity, workers=args.workers)
        d = rep["direction"]
        print(f"\nNote-reader lift: the notes changed the queue for "
              f"{rep['changed']} of {rep['noted_students']} noted students "
              f"({d['escalated']} up, {d['de_escalated']} down, {d['review']} to review).")
        for e in rep["examples"]:
            print(f"  {e['student_id']}: {e['rules_only']:>18}  ->  {e['with_notes']:<18}  ({e['note_state']})")
        return

    if args.v2:
        rep = run_v2(use_llm=not args.no_llm, as_of_date=args.as_of_date,
                     capacity=args.capacity, invocation=INVOCATION, workers=args.workers)
        s, e = rep["queue"], rep["effectiveness"]
        print(f"\nBoon Academy v2 — backend: {rep['backend']} · as of {args.as_of_date}")
        print(f"  KPI: {s['failers_contacted_since_quiz']}/{s['failers_total']} failers contacted since "
              f"Quiz 1 ({s['contact_rate_pct']}%) · {s['failers_with_action_today']}/{s['failers_total']} "
              f"have a ready action today · {s['days_to_next_quiz']} days left")
        print(f"  queue: {s['priority_actions']} calls/1-on-1s (cap {s['capacity_per_facilitator']}) · "
              f"{s['messages_today']} messages (uncapped) · {s['human_review']} human-review")
        if rep["backtest"]:
            print(f"  backtest: AUC {rep['backtest']['auc']} · "
                  f"precision@{rep['backtest']['k']} {rep['backtest']['precision_at_k']}")
        if rep["extractor_eval"]:
            x = rep["extractor_eval"]
            print(f"  extractor vs gold: {x['strict_agreement_pct']}% strict / "
                  f"{x['lenient_agreement_pct']}% lenient · kappa {x['cohen_kappa_state']}")
        if rep["lift"]:
            print(f"  lift: notes changed {rep['lift']['changed']}/{rep['lift']['noted_students']} noted students")
        print(f"  contact≠effect (descriptive): {e['by_outcome']} · escalate: {rep['escalate']}")
        print("  outputs/ -> queue.* · v2_report.md · extractor_eval.json · backtest_day9.json · "
              "effectiveness_report.json · fairness_report.json · lift_report.json")
        return

    result = run(use_llm=not args.no_llm, as_of_date=args.as_of_date,
                 capacity=args.capacity, campus=args.campus, invocation=INVOCATION,
                 workers=args.workers)
    s = result["summary"]
    print(f"\nBoon Academy triage — backend: {result['backend']} · as of {s['as_of_date']}")
    print(f"  {s['students_total']} students -> {s['priority_actions']} calls/1-on-1s, "
          f"{s['messages_today']} messages, {s['human_review']} human-review, "
          f"{s['students_left_alone']} left alone")
    print(f"  KPI: {s['failers_with_action_today']}/{s['failers_total']} failers have a ready action "
          f"· {s['failers_contacted_since_quiz']} contacted since Quiz 1 ({s['contact_rate_pct']}%)")
    print(f"  by priority: {s['by_priority']}")
    print("  outputs/ -> queue.csv · queue.json · action_queue.html · run_log.json")

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
