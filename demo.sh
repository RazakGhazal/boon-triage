#!/usr/bin/env bash
#
# demo.sh — narrated, one-command live demo for the video.
#   ./demo.sh              run it (opens the queue in your browser at the end)
#   DEMO_NO_OPEN=1 ./demo.sh   run it without auto-opening the browser
#
# It runs in its OWN output dir (outputs/demo-live, gitignored) with a fresh
# cache, so you SEE Gemini read each Arabic note live (~30s) — and the real
# committed outputs/ (the full-cohort `make demo` run) are never touched.
#
set -euo pipefail
cd "$(dirname "$0")"
unset GOOGLE_API_KEY 2>/dev/null || true      # use only the valid key from .env
export OUTPUT_DIR="$(pwd)/outputs/demo-live"  # keep the committed outputs/ pristine
rm -rf "$OUTPUT_DIR"                          # fresh dir + fresh cache = live API calls
PY="${PYTHON:-python3}"

step(){ printf '\n\033[1;36m━━━  %s  ━━━\033[0m\n\n' "$1"; sleep 1.5; }

clear
step "BOON ACADEMY · intervention triage"
echo "Only ~30% of failing students get help before the next quiz."
echo "The warning signs are split between the LMS numbers and the facilitators'"
echo "own Arabic notes — and nobody reads both together."

step "Watch Gemini READ the notes, live  (real API calls, one campus)"
echo "Fresh cache in outputs/demo-live — every call below is genuine, not replayed…"
sleep 1
$PY main.py --campus C01 --workers 2           # streams:  · [n] Sxxx  Arabic note → state

step "The product a facilitator opens Monday morning"
echo "→ outputs/demo-live/action_queue.html"
if [ "${DEMO_NO_OPEN:-0}" != "1" ]; then
  open outputs/demo-live/action_queue.html 2>/dev/null || echo "  (open it manually)"
fi
echo
echo "Walk these three — where the notes change the answer (all in this campus):"
echo "   S005  looks fine on the numbers — note says the contact FAILED twice → ESCALATE"
echo "   S023  passed the quiz (88), attendance cliffed → the SILENT DROPOUT"
echo "   S017  passing numbers, but the note reveals a family crisis → SUPPORT (Medium)"
echo
echo "…and half the campus was LEFT ALONE — the system knows when NOT to act (incl."
echo "sick students whose parents were already reached: check-in message, not a call)."
echo
printf '\033[1;32mDone.\033[0m  Rules scored the numbers · Gemini read the Arabic · fusion ranked them.\n'
echo "(committed outputs/ untouched — this demo ran in outputs/demo-live)"
