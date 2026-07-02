"""The note-reader: the ONE place the LLM is used, because it is the one job a
rule cannot do — read Saudi-dialect Arabic prose and say what's actually going on.

Extractor, not oracle: it emits a small structured state; rules decide.
Two backends behind one interface (NoLLM for the --no-llm lift baseline, Gemini
for the real run). Native structured output (responseSchema) guarantees valid
JSON. Every extraction is faithfulness-checked (the quoted span must really
appear in a note) and cached by content hash so re-runs are cheap + deterministic.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Literal, Optional

from . import config as C
from .ingest import StudentRecord

State = Literal["none", "improving", "explained", "needs_help", "failing", "refused"]
Blocker = Literal["academic", "motivation", "family", "health", "logistics", "unknown"]


@dataclass
class NoteState:
    student_id: str
    state: str = "none"
    blocker: str = "unknown"         # what stands in the way (academic/motivation/...)
    summary: str = ""
    root_cause: str = ""
    suggested_action: str = "none"   # call_parent | one_on_one | message | none
    draft_message: str = ""          # Arabic WhatsApp draft with a literal {name} placeholder
    evidence: str = ""               # exact Arabic span from a note
    concern: str = "neutral"         # low | neutral | worried | urgent
    confidence: str = "high"         # low | medium | high
    faithful: bool = True


# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = """You read a single Boon Academy facilitator's note thread about ONE student.
The notes are short, informal Saudi-dialect Arabic, in chronological order, each line
prefixed [Day N]. Quiz 1 was Day 10; the next quiz is Day 20. The facilitator's job is
to help failing students (call the parent, 1-on-1 tutoring, motivational messages).

You never see the attendance/quiz numbers — a rules engine scores those. Your ONLY job
is to report what the PROSE says, weighting the most recent days. Return JSON:

- state (as of the latest notes):
    "improving"  was struggling but is now clearly better, OR an intervention is working.
    "explained"  the problem (usually an absence) has a known, managed, likely temporary
                 cause — illness, a family event — AND the parent is aware or was
                 contacted. Monitoring is enough for now.
    "needs_help" a real problem (academic, motivational, family, emotional) with no
                 working intervention in place yet — including notes that only say
                 "we must intervene".
    "failing"    help WAS attempted and it is NOT working. This includes: a student who
                 stopped coming while calls/WhatsApp to the parents go unanswered or
                 undelivered (the contact channel itself is failing — needs escalation);
                 and guidance that was given but behavior is unchanged ("لسا نفس الشي").
    "refused"    the parent or student EXPLICITLY declined or pushed back on offered
                 help (defensive parent, rejected offer, quit the program). A student
                 merely not doing exercises is needs_help, not refused.
    "none"       purely administrative or positive-only notes; nothing to act on.
- blocker: what stands in the way — academic | motivation | family | health |
  logistics | unknown. (Fear of hard questions / low confidence = motivation; a parent
  unaware of the program = family; schedule/transport/night-shift issues = logistics.)
- summary: ONE plain sentence (English) — what is going on right now.
- root_cause: the specific cause if stated (e.g. "late-night gaming"), else "".
- suggested_action: one of call_parent | one_on_one | message | none.
- draft_message: a short WhatsApp message in SIMPLE, WARM Modern Standard Arabic (فصحى
  مبسطة — never stiff/bureaucratic), addressed to the PARENT and sent BY the facilitator.
  Refer to the student ONLY as {name} — a literal placeholder the system fills in later
  (you are never given the real name). It must: cite ONE specific fact from the notes;
  be improvement-focused (what to do next, not blame); propose exactly ONE doable step
  (NEVER a meeting or anything requiring scheduling); be 2-3 sentences. "" if no
  outreach is warranted.
- evidence: copy an EXACT short Arabic span from the notes that justifies the state.
  REQUIRED for every state except "none" — if you cannot point to a real span, the
  state must be "none".
- concern: low | neutral | worried | urgent (how worried the facilitator sounds).
- confidence: low | medium | high. Use "low" when the notes are vague or you are guessing.

Be faithful. Do not invent facts. Vague worry with no clear picture = "needs_help"
with confidence="low" rather than a guess."""

# Few-shots are FICTIONAL threads (not students from the dataset) so the gold-set
# evaluation in eval/ stays untouched by memorised examples.
FEWSHOT = [
    (
        'notes:\n[Day 5] اتصلت على ام فهد بخصوص غيابه. قالت يسهر على الالعاب ووعدت تراقب الجوال\n'
        '[Day 12] فهد لسا ما يجي. اتصلت مرتين على الام، ما ردت. قلقان عليه',
        {"state": "failing", "blocker": "motivation",
         "summary": "Contact about late-night gaming went nowhere; the mother has stopped answering and he is still absent.",
         "root_cause": "late-night gaming", "suggested_action": "call_parent",
         "draft_message": "السلام عليكم، نفتقد {name} في الحصص هذه الأيام ويهمنا الاطمئنان. نعرف أن تنظيم وقت الألعاب ليس سهلًا، لكن الاتفاق على وقت ثابت لإغلاق الجهاز قبل النوم يصنع فرقًا واضحًا قبل الاختبار القادم — ونحن معكم خطوة بخطوة.",
         "evidence": "اتصلت مرتين على الام، ما ردت", "concern": "urgent", "confidence": "high"},
    ),
    (
        'notes:\n[Day 4] ريم تحضر كامل بس ما تحل تمارين. تواصلت مع امها - ما كانت تدري ان التمارين جزء اساسي من البرنامج\n'
        '[Day 13] فرق واضح! ريم صارت تحل يوميا والام تتابع معها. قصة نجاح',
        {"state": "improving", "blocker": "family",
         "summary": "Big turnaround on daily practice after the mother learned it was required and got involved.",
         "root_cause": "family was unaware practice is required", "suggested_action": "message",
         "draft_message": "ما شاء الله، الفرق واضح منذ بدأتم المتابعة — {name} الآن على المسار الصحيح. تثبيت عادة 10 أسئلة يوميًا سيحافظ على هذا التقدّم قبل الاختبار القادم.",
         "evidence": "فرق واضح!", "concern": "low", "confidence": "high"},
    ),
    (
        'notes:\n[Day 13] سلطان جا ٢٠ دقيقة وطلع. اتصلت على ابوه - قال عنده حرارة\n'
        '[Day 14] سلطان غايب اليوم. ابوه يقول يحتاج كم يوم راحة وبيرجع ان شاء الله',
        {"state": "explained", "blocker": "health",
         "summary": "Absent with a fever; the father is aware and expects him back after a few days of rest.",
         "root_cause": "illness (fever)", "suggested_action": "message",
         "draft_message": "السلام عليكم، نطمئن على صحة {name} ونتمنى الشفاء العاجل. لا داعي لأي قلق بخصوص الحصص — متى ما تحسّنت الحالة يسعدنا رجوع {name} بالتدريج، ونحن موجودون لأي مساعدة.",
         "evidence": "يحتاج كم يوم راحة", "concern": "neutral", "confidence": "high"},
    ),
    (
        'notes:\n[Day 12] رنا ما جت من يومين، وكانت من الممتازات\n'
        '[Day 14] لسا غايبه. اتصلت على امها مرتين وارسلت واتساب، ما في رد. قلقانه',
        {"state": "failing", "blocker": "unknown",
         "summary": "A previously excellent student has vanished and the mother is not answering calls or WhatsApp.",
         "root_cause": "", "suggested_action": "call_parent",
         "draft_message": "السلام عليكم، نفتقد {name} في الحصص منذ يومين ويهمنا كثيرًا الاطمئنان أن كل شيء بخير. نرجو التكرم بالرد على هذه الرسالة أو تحديد وقت يناسبكم للاتصال — وجود {name} في حصة الغد يفرق كثيرًا قبل الاختبار القادم.",
         "evidence": "اتصلت على امها مرتين وارسلت واتساب، ما في رد", "concern": "urgent", "confidence": "high"},
    ),
]


# --------------------------------------------------------------------------- #
class NoLLMBackend:
    """Baseline: read nothing. Used for the --no-llm lift measurement."""
    name = "no-llm"

    def extract(self, payload: dict) -> dict:
        return {"state": "none", "confidence": "high"}


class GeminiBackend:
    """Gemini 2.5 Flash Lite with native structured output (responseSchema)."""
    name = "gemini"

    def __init__(self, api_key: str = None, model: str = None):
        from google import genai  # imported lazily so --no-llm needs no key/SDK
        self._genai = genai
        self.client = genai.Client(api_key=api_key or C.GEMINI_API_KEY)
        self.model = model or C.GEMINI_MODEL

    def _schema(self):
        from pydantic import BaseModel

        class Extraction(BaseModel):
            state: State
            blocker: Blocker = "unknown"
            summary: str
            root_cause: str = ""
            suggested_action: Literal["call_parent", "one_on_one", "message", "none"] = "none"
            draft_message: str = ""
            evidence: str = ""
            concern: Literal["low", "neutral", "worried", "urgent"] = "neutral"
            confidence: Literal["low", "medium", "high"] = "medium"

        return Extraction

    def extract(self, payload: dict) -> dict:
        from google.genai import errors, types

        shots = "\n\n".join(f"INPUT:\n{i}\nOUTPUT:\n{json.dumps(o, ensure_ascii=False)}" for i, o in FEWSHOT)
        user = (
            f"{shots}\n\nNow extract for this student.\nINPUT:\n"
            f"notes:\n{payload['notes']}\nOUTPUT:"
        )
        cfg = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0,
            response_mime_type="application/json",
            response_schema=self._schema(),
        )
        # retry transient server/rate errors with backoff (a batch job must survive spikes)
        last = None
        for attempt in range(4):
            try:
                resp = self.client.models.generate_content(model=self.model, contents=user, config=cfg)
                if getattr(resp, "parsed", None) is not None:
                    return resp.parsed.model_dump()
                return json.loads(resp.text)
            except errors.APIError as e:
                if getattr(e, "code", None) in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(3 * (2 ** attempt))  # 3s, 6s, 12s
                    last = e
                    continue
                raise
        raise last


# --------------------------------------------------------------------------- #
def _cache_key(payload: dict) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(f"{C.PROMPT_VERSION}|{C.GEMINI_MODEL}|{blob}".encode()).hexdigest()[:20]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _faithful(evidence: str, note_text: str) -> bool:
    """The quoted span must really appear in the student's notes."""
    e = _norm(evidence)
    return bool(e) and e in _norm(note_text)


def extract_states(records: dict[str, StudentRecord], backend, use_cache: bool = True) -> dict[str, NoteState]:
    states: dict[str, NoteState] = {}
    unavailable: list[str] = []
    use_cache = use_cache and getattr(backend, "name", "") != "no-llm"  # rules-only is free; don't cache it
    os.makedirs(C.CACHE_DIR, exist_ok=True)
    is_gemini = getattr(backend, "name", "") == "gemini"
    live_n = 0  # notes actually sent to the LLM this run (cache misses) — for visible progress

    for sid, r in records.items():
        if not r.has_notes:
            states[sid] = NoteState(student_id=sid, state="none", confidence="high")
            continue

        payload = r.to_llm_payload()
        raw: Optional[dict] = None
        was_live = False
        cache_path = os.path.join(C.CACHE_DIR, f"{backend.name}_{_cache_key(payload)}.json")
        if use_cache and os.path.exists(cache_path):
            raw = json.load(open(cache_path, encoding="utf-8"))
        if raw is None:
            try:
                raw = backend.extract(payload)
                was_live = True
            except Exception:  # persistent transient failure — rules-only for this student, don't cache
                unavailable.append(sid)
                states[sid] = NoteState(student_id=sid, state="none", confidence="low",
                                        summary="(note-read unavailable this run — service busy)")
                continue
            if use_cache:
                json.dump(raw, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False)

        ns = NoteState(
            student_id=sid,
            state=raw.get("state", "none"),
            blocker=raw.get("blocker", "unknown"),
            summary=raw.get("summary", ""),
            root_cause=raw.get("root_cause", ""),
            suggested_action=raw.get("suggested_action", "none"),
            draft_message=raw.get("draft_message", ""),
            evidence=raw.get("evidence", ""),
            concern=raw.get("concern", "neutral"),
            confidence=raw.get("confidence", "medium"),
        )
        # faithfulness gate: a non-'none' state MUST be backed by a verbatim span from a real
        # note. A fabricated OR MISSING quote is downgraded to low-confidence (→ review lane),
        # never trusted — so "every claim is grounded in a real Arabic span" is actually true.
        if ns.state != "none" and not (ns.evidence and _faithful(ns.evidence, r.note_text_concat)):
            ns.faithful = False
            ns.evidence = ""
            ns.confidence = "low"
        states[sid] = ns
        if was_live and is_gemini:  # only real LLM calls print; a warm cache stays silent & instant
            live_n += 1
            print(f"  · [{live_n:>2}] {sid}  Arabic note → {ns.state}", flush=True)
    if unavailable:
        print(f"  [note-reader] {len(unavailable)} students fell back to rules-only this run "
              f"(service busy); re-run to fill them from cache.")
    return states


def make_backend(use_llm: bool):
    if not use_llm:
        return NoLLMBackend()
    if not C.GEMINI_API_KEY:
        raise RuntimeError(
            "No GEMINI_API_KEY found. Put it in .env (GEMINI_API_KEY=...) "
            "or run with --no-llm for the rules-only baseline."
        )
    return GeminiBackend()
