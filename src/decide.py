"""Fusion: combine NEED (numbers) with STATE (notes) into one action.

Deliberately 3 rules, not a matrix. The whole point of reading the notes is to
correct the two cases where the numbers lie:

  UP    a failing/refused intervention must NOT be de-prioritized just because
        the student was recently contacted               -> S005, S004, S123
  DOWN  a working intervention whose metrics agree gets demoted (give capacity
        back) — but ONLY if the numbers aren't themselves failing  -> S145, S070
        (the "and the numbers agree" guard is what stops a soft note from
         rescuing a quiz-failing crammer like S051)
  REVIEW a low-confidence / vague note is flagged for a human, never auto-acted -> S013

Surfacing: a student is on the queue if the numbers flag them OR the note is
non-positive. That one OR is what catches S017 (clean numbers, crisis note).
"""
from __future__ import annotations

from dataclasses import dataclass

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
    concern: str
    confidence: str
    evidence: str
    phone_masked: str
    phone_flag: str
    note_changed_priority: bool = False  # for the --no-llm lift measurement


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
    changed = False

    s = ns.state
    if s in ("failing", "refused"):
        priority = _bump(base, +1)
        if not _ge(priority, "High"):
            priority = "High"  # a failing/refused intervention is at least High
        note_reason = ("an attempted intervention is failing — recent contact has NOT "
                       "resolved it, so this is NOT lower priority")
        changed = priority != base
    elif s == "on_track" and not r.quiz_failed and not r.recent_cliff:
        priority = _bump(base, -1)
        note_reason = ("the facilitator's intervention is working and the metrics agree "
                       "— monitor, don't escalate")
        changed = priority != base

    if r.has_notes and ns.confidence == "low" and s not in ("on_track",):
        lane = "human_review"
        note_reason = note_reason or "the note is ambiguous — needs a human read before acting"

    surfaced = _ge(base, "Medium") or s in ("needs_help", "failing", "refused") or lane == "human_review"

    # metrics look fine but the note reveals something — make sure it's visible
    if surfaced and s == "needs_help" and not _ge(priority, "Medium"):
        priority = "Medium"
        note_reason = note_reason or "the metrics look fine but the note reveals a problem the numbers miss"
        changed = True

    if not surfaced:
        lane = "leave_alone"

    if note_reason:
        reasons.append(note_reason)

    # action
    if ns.suggested_action and ns.suggested_action != "none":
        action = ns.suggested_action
    elif lane == "human_review":
        action = "review"
    elif s in ("failing", "refused") or r.recent_cliff or risk.signals.get("chronic_low_att"):
        action = "call_parent"
    elif risk.signals.get("low_practice"):
        action = "one_on_one"
    else:
        action = "message"

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
        draft_message=ns.draft_message,
        note_state=s,
        concern=ns.concern,
        confidence=ns.confidence,
        evidence=ns.evidence,
        phone_masked=_mask_phone(r.parent_phone_e164),
        phone_flag=r.parent_phone_flag,
        note_changed_priority=changed,
    )


def _numbers_story(risk: Risk) -> str:
    if risk.reasons:
        return risk.reasons[0][0].upper() + risk.reasons[0][1:]
    return "No risk signals on the numbers."
