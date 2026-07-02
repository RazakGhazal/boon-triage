"""Fusion: combine NEED (numbers) with STATE (notes) into one action.

Deliberately 3 rule FAMILIES, not a matrix. A note can move a student one tier,
floor them, or send them to a human — it can never zero anyone out, and the
dangerous direction (de-escalation) always needs the numbers' consent:

  UP     a failing/refused intervention is at least High — recent contact must
         NOT hide a student whose contact isn't working        -> S005, S123
  DOWN   improving + the numbers agree -> one tier down (capacity back) -> S156
         explained (illness/family event, parent already engaged) -> monitor:
         a known, managed absence must not burn a call slot the day after the
         parent was reached — the numbers alone would score it Critical -> S141
  REVIEW a low-confidence / vague / unevidenced read goes to a human,
         never auto-acted                                       -> S013

Surfacing: by FINAL priority (post-fusion) or a non-positive note state. That
one OR is what catches S017 (clean numbers, crisis note).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .drafts import template_draft
from .ingest import StudentRecord
from .notes import NoteState
from .risk import Risk

TIER_ORDER = ["Low", "Medium", "High", "Critical"]


def _bump(tier: str, delta: int) -> str:
    i = max(0, min(len(TIER_ORDER) - 1, TIER_ORDER.index(tier) + delta))
    return TIER_ORDER[i]


def _ge(a: str, b: str) -> bool:
    return TIER_ORDER.index(a) >= TIER_ORDER.index(b)


@dataclass
class ActionRow:
    student_id: str
    facilitator_email: str
    campus_id: str
    learning_track: str
    priority: str
    base_tier: str
    risk_score: int
    lane: str           # queue | human_review | leave_alone
    story: str
    reasons: list
    action_type: str    # call_parent | one_on_one | message | review
    draft_message: str
    note_state: str
    blocker: str
    concern: str
    confidence: str
    evidence: str
    phone_masked: str
    phone_flag: str
    is_failer: bool
    contacted_since_quiz: bool
    last_note_day: Optional[int]
    note_changed_priority: bool = False  # for the --lift measurement
    call_waitlisted: bool = False        # heavy action beyond capacity: message today, call when free


def _mask_phone(e164):
    # never echo the raw contact field — a dirty phone (email/invalid) would leak PII;
    # the phone_flag column already tells the facilitator why it's unusable
    if e164:
        return e164[:5] + "•" * max(0, len(e164) - 7) + e164[-2:]
    return "[no usable phone]"


def decide(r: StudentRecord, risk: Risk, ns: NoteState) -> ActionRow:
    base = risk.tier
    priority = base
    lane = "queue"
    reasons = list(risk.reasons)
    note_reason = None

    s = ns.state
    if s in ("failing", "refused"):
        priority = _bump(base, +1)
        if not _ge(priority, "High"):
            priority = "High"  # a failing/refused intervention is at least High
        note_reason = ("an attempted intervention is failing — recent contact has NOT "
                       "resolved it, so this is NOT lower priority")
    elif s == "improving" and ns.confidence != "low" and not r.quiz_failed and not r.recent_cliff:
        priority = _bump(base, -1)
        note_reason = ("the facilitator's intervention is working and the metrics agree "
                       "— monitor, don't escalate")
    elif s == "explained" and ns.confidence != "low":
        # the collapse has a known, managed cause and the parent is already engaged;
        # keep visible (check-in message), never top-of-queue
        priority = "Medium" if (r.quiz_failed or _ge(base, "High")) else "Low"
        note_reason = ("the absence is explained (illness/family, parent already engaged) "
                       "— a check-in, not another call slot")
    elif s == "needs_help" and not _ge(priority, "Medium"):
        priority = "Medium"
        note_reason = "the metrics look fine but the note reveals a problem the numbers miss"

    changed = priority != base

    if r.has_notes and ns.confidence == "low" and s != "improving":
        lane = "human_review"
        note_reason = note_reason or "the note is ambiguous — needs a human read before acting"

    surfaced = _ge(priority, "Medium") or s in ("failing", "refused") or lane == "human_review"
    if not surfaced:
        lane = "leave_alone"

    if note_reason:
        reasons.append(note_reason)

    # action — the explained lane is forced to a message: the parent was reached already
    if lane == "human_review":
        action = "review"
    elif s == "explained":
        action = "message"
    elif ns.suggested_action and ns.suggested_action != "none":
        action = ns.suggested_action
    elif s in ("failing", "refused") or r.recent_cliff or risk.signals.get("quiz_absent") \
            or risk.signals.get("chronic_low_att"):
        action = "call_parent"
    elif risk.signals.get("low_practice"):
        action = "one_on_one"
    else:
        action = "message"

    # draft: the LLM's (from the notes) if there is one, else a template from the
    # metrics — every surfaced student leaves with a ready message, not homework
    draft = (ns.draft_message or "").replace("{name}", r.first_name)
    if not draft and surfaced and lane != "human_review":
        draft = template_draft(r, risk, s)

    story = ns.summary if (r.has_notes and ns.summary) else _numbers_story(risk)

    return ActionRow(
        student_id=r.student_id,
        facilitator_email=r.facilitator_email,
        campus_id=r.campus_id,
        learning_track=r.learning_track,
        priority=priority,
        base_tier=base,
        risk_score=risk.score,
        lane=lane,
        story=story,
        reasons=reasons,
        action_type=action,
        draft_message=draft,
        note_state=s,
        blocker=ns.blocker,
        concern=ns.concern,
        confidence=ns.confidence,
        evidence=ns.evidence,
        phone_masked=_mask_phone(r.parent_phone_e164),
        phone_flag=r.parent_phone_flag,
        is_failer=r.quiz_failed,
        contacted_since_quiz=r.contacted_since_quiz,
        last_note_day=r.last_note_day,
        note_changed_priority=changed,
    )


def _numbers_story(risk: Risk) -> str:
    if risk.reasons:
        return risk.reasons[0][0].upper() + risk.reasons[0][1:]
    return "No risk signals on the numbers."
