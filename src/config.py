"""Central config. All tunables live here; nothing reads os.environ elsewhere.

Reproducibility rule: the pipeline's notion of "today" is AS_OF_DATE, never now().
That keeps committed outputs byte-stable and the demo replayable.
"""
import os

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_dotenv(path: str) -> None:
    """Tiny .env loader (no extra dependency). Does not override real env vars."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv(os.path.join(_HERE, ".env"))

# --- the case clock (Day 14; Quiz 1 = Day 10; Quiz 2 = Day 20) ---
# NOTE for 100 campuses: this calendar becomes a per-campus data table (each
# campus has its own quiz dates and active days); the pipeline already takes
# every date from here, so the swap is confined to this block.
AS_OF_DATE = os.environ.get("AS_OF_DATE", "2025-10-14")
PROGRAM_START = "2025-10-01"   # Day 1
QUIZ1_DATE = "2025-10-10"
NEXT_QUIZ_DATE = "2025-10-20"

# active class days actually present in the data (Fri/Sat weekends are absent)
ACTIVE_DATES = [
    "2025-10-01", "2025-10-02", "2025-10-03", "2025-10-04",
    "2025-10-07", "2025-10-08", "2025-10-09", "2025-10-10",
    "2025-10-13", "2025-10-14",
]
RECENT_DATES = ["2025-10-13", "2025-10-14"]  # last 2 active days = the "cliff" window

PASS_THRESHOLD = 60
CORRUPT_TARGET_THRESHOLD = 60  # a "target_score" below the pass mark is garbage data

# --- risk thresholds (tuned against the data; see tests/test_cast.py) ---
LOW_ATTENDANCE_MIN = 40    # recent avg session minutes below this = chronically low
LOW_PRACTICE_MEDIAN = 5    # median practice questions/day below this = disengaged
CLIFF_BASELINE_MIN = 60    # "was attending well..."
CLIFF_RECENT_MAX = 10      # "...then collapsed to near-zero in the last days"

# tier point cutoffs
TIER_CUTOFFS = [(6, "Critical"), (4, "High"), (2, "Medium"), (0, "Low")]

# --- product ---
# Capacity bounds only the EXPENSIVE actions (calls, 1-on-1s). Drafted WhatsApp
# messages cost ~1 minute to review+send, so they are never capped — otherwise a
# facilitator with 16 quiz-failers (facilitator8) could mathematically never
# reach the 80% intervention target under any ranking.
DEFAULT_CAPACITY = 8  # max calls/1-on-1s surfaced per facilitator before Day 20

# --- paths ---
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(_HERE, "data"))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.path.join(_HERE, "outputs"))
CACHE_DIR = os.environ.get("CACHE_DIR", os.path.join(OUTPUT_DIR, ".cache"))

# --- LLM (the note-reader; one swappable seam) ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
# v3:   notes-only payload (no metrics), dated threads, blocker_type, evidence required
# v3.1: eval-driven fix — the gold set caught failing-recall 0.15 (unreachable-parent
#       dropouts read as needs_help); sharpened the failing definition + 1 few-shot
# v3.2: student_gender in the payload (never the name) — Arabic agreement in the
#       {name}-placeholder draft must follow the ROSTER child, not names in notes
PROMPT_VERSION = "v3.2"
