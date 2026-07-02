"""Deterministic Arabic drafts for students the LLM has no note thread for.

The KPI is coverage: every quiz-failer needs at least the cheap intervention (a
personalized parent message) before Day 20. The LLM only drafts from notes —
which 62% of students don't have — so the numbers-only majority get a template
draft filled from their own metrics. No LLM involved: the message must never
say more than the numbers we can show.

Style rules (same as the LLM's): simple warm MSA, one specific fact, one doable
step, never a meeting, 2–3 sentences. Templates are written gender-safe: the
grammatical subject is the metric (حضور/تمارين/نتيجة), never the student, so no
verb or pronoun has to guess the student's gender. `{name}` is filled locally —
names never travel to any API.
"""
from __future__ import annotations

from . import config as C
from .ingest import StudentRecord
from .risk import Risk

_GREETING = "السلام عليكم، معكم مُيسِّر {name} في بوون أكاديمي. "

_CLIFF = (
    "لاحظنا أن حضور {name} توقف تقريبًا في آخر يومين بعد فترة التزام ممتازة، "
    "ويهمنا الاطمئنان أن كل شيء على ما يرام. "
    "نقترح خطوة واحدة: تشجيع {name} على حضور حصة الغد كاملة، وسنتابع نحن الباقي قبل الاختبار القادم."
)
_QUIZ_ABSENT = (
    "لاحظنا غياب {name} عن الاختبار الأخير، ونودّ الاطمئنان ومعرفة ما إذا كان هناك ظرف معيّن. "
    "يهمنا ترتيب تعويض بسيط للاختبار — يكفي إبلاغنا باليوم المناسب هذا الأسبوع."
)
_CHRONIC = (
    "متوسط حضور {name} في الفترة الأخيرة حوالي {recent} دقيقة من حصة مدتها 90 دقيقة. "
    "الحصة الكاملة تصنع فرقًا واضحًا قبل الاختبار القادم، "
    "ونقترح هدفًا بسيطًا لهذا الأسبوع: حضور الحصة من أولها إلى آخرها."
)
_FAIL = (
    "نتيجة {name} في الاختبار الأخير كانت {score} من 100، والوقت كافٍ تمامًا للتحسّن قبل الاختبار القادم. "
    "نقترح خطوة واحدة: حل 10 أسئلة تدريب يوميًا هذا الأسبوع، وسنتابع التقدّم أولًا بأول."
)
_LOW_PRACTICE = (
    "حضور {name} منتظم وهذا ممتاز، لكن التمارين اليومية شبه متوقفة. "
    "التمارين هي ما يرفع الدرجات فعليًا — نقترح البدء بـ10 أسئلة يوميًا قبل الاختبار القادم."
)
_CHECK_IN = (
    "نطمئن على {name} ونتمنى أن يكون كل شيء على ما يرام. "
    "متى ما كان الوضع مناسبًا يسعدنا رجوع {name} للحصص بالتدريج، ونحن موجودون لأي مساعدة."
)


def template_draft(r: StudentRecord, risk: Risk, note_state: str) -> str:
    """Pick ONE template by the dominant signal (severity order mirrors risk.py)."""
    if note_state == "explained":
        body = _CHECK_IN
    elif risk.signals.get("cliff"):
        body = _CLIFF
    elif risk.signals.get("quiz_absent"):
        body = _QUIZ_ABSENT
    elif risk.signals.get("fail"):
        body = _FAIL.replace("{score}", str(r.quiz_score))
    elif risk.signals.get("chronic_low_att"):
        body = _CHRONIC.replace("{recent}", f"{r.attendance_recent_min:.0f}")
    elif risk.signals.get("low_practice"):
        body = _LOW_PRACTICE
    else:
        body = _CHECK_IN
    return (_GREETING + body).replace("{name}", r.first_name)
