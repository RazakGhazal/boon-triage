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

State = Literal["none", "on_track", "needs_help", "failing", "refused"]


@dataclass
class NoteState:
    student_id: str
    state: str = "none"
    summary: str = ""
    root_cause: str = ""
    suggested_action: str = "none"   # call_parent | one_on_one | message | none
    draft_message: str = ""          # short Arabic WhatsApp draft (LLM only)
    evidence: str = ""               # exact Arabic span from a note
    concern: str = "neutral"         # low | neutral | worried | urgent
    confidence: str = "high"         # low | medium | high
    faithful: bool = True


# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = """You read a single Boon Academy facilitator's notes about ONE student.
The notes are short, informal Saudi-dialect Arabic. The facilitator's job is to help
failing students (call the parent, 1-on-1 tutoring, motivational messages).

Your ONLY job is to report the STATE of any intervention — you do not score risk.
Return JSON with these fields:

- state:
    "on_track"   the student was struggling but is now improving, OR an intervention
                 is clearly working / the trajectory is positive.
    "failing"    an intervention was tried but is NOT working — parent or student
                 unresponsive, problem worsening, facilitator worried/urgent.
    "refused"    the parent or student declined help or pushed back.
    "needs_help" the note reveals a real problem or crisis (academic, family,
                 emotional) and the student needs attention, but no working
                 intervention is in place yet.
    "none"       purely descriptive/administrative, or no clear intervention signal.
- summary: ONE plain sentence (English) — what is going on for this student.
- root_cause: the underlying cause if stated (e.g. gaming, family issue, unaware of
  program, lost motivation), else "".
- suggested_action: one of call_parent | one_on_one | message | none.
- draft_message: a short WhatsApp message in SIMPLE, WARM Modern Standard Arabic (فصحى
  مبسطة — never stiff/bureaucratic), addressed to the PARENT and sent BY the named
  facilitator. It must: cite ONE specific fact about the student; be improvement-focused
  (what to do next, not praise or blame); propose exactly ONE doable step (NEVER a meeting
  or anything requiring scheduling); be 2-3 sentences. "" if no outreach is warranted.
- evidence: copy an EXACT short Arabic span from the notes that justifies the state.
- concern: low | neutral | worried | urgent (how worried the facilitator sounds).
- confidence: low | medium | high. Use "low" when the notes are vague or you are guessing.

Be faithful. Do not invent facts. If the notes are too vague to judge, say state="needs_help"
or "none" with confidence="low" rather than guessing."""

FEWSHOT = [
    (
        'notes: "اتصلت مرتين على الام، ما ردت. قلقانه عليه. بدا باللعب وصار اسوأ"\nmetrics: quiz 85, attendance collapsed',
        {"state": "failing", "summary": "Repeatedly contacted the mother about worsening gaming; no response.",
         "root_cause": "late-night gaming", "suggested_action": "call_parent",
         "draft_message": "السلام عليكم، أحمد طالب قادر لكن حضوره ومذاكرته تراجعا هذا الأسبوع بسبب السهر على الألعاب. لو نتفق معه على وقت ثابت للنوم وإغلاق الألعاب قبله بساعة، نتوقّع تحسّنًا واضحًا قبل الاختبار القادم.",
         "evidence": "ما ردت. قلقانه عليه", "concern": "urgent", "confidence": "high"},
    ),
    (
        'notes: "تحول كبير! صار يحضر بانتظام، الاب صار متفاعل. قصة نجاح"\nmetrics: quiz 72, attendance rising',
        {"state": "on_track", "summary": "Big turnaround after the father got involved; attending regularly now.",
         "root_cause": "family was unaware of the program", "suggested_action": "message",
         "draft_message": "ما شاء الله، يوسف تحسّن كثيرًا بعد متابعتكم — حضوره ومذاكرته في ارتفاع. تشجيعه على حل ١٠ أسئلة يوميًا سيثبّت هذا التقدّم قبل الاختبار.",
         "evidence": "تحول كبير", "concern": "low", "confidence": "high"},
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
        from pydantic import BaseModel, Field

        class Extraction(BaseModel):
            state: Literal["none", "on_track", "needs_help", "failing", "refused"]
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
            f"notes:\n{payload['notes']}\nmetrics: {json.dumps(payload['metrics'], ensure_ascii=False)}\nOUTPUT:"
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

    for sid, r in records.items():
        if not r.has_notes:
            states[sid] = NoteState(student_id=sid, state="none", confidence="high")
            continue

        payload = r.to_llm_payload()
        raw: Optional[dict] = None
        cache_path = os.path.join(C.CACHE_DIR, f"{backend.name}_{_cache_key(payload)}.json")
        if use_cache and os.path.exists(cache_path):
            raw = json.load(open(cache_path, encoding="utf-8"))
        if raw is None:
            try:
                raw = backend.extract(payload)
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
            summary=raw.get("summary", ""),
            root_cause=raw.get("root_cause", ""),
            suggested_action=raw.get("suggested_action", "none"),
            draft_message=raw.get("draft_message", ""),
            evidence=raw.get("evidence", ""),
            concern=raw.get("concern", "neutral"),
            confidence=raw.get("confidence", "medium"),
        )
        # faithfulness gate: a fabricated quote is downgraded, never trusted
        if ns.state != "none" and ns.evidence and not _faithful(ns.evidence, r.note_text_concat):
            ns.faithful = False
            ns.evidence = ""
            ns.confidence = "low"
        states[sid] = ns
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
