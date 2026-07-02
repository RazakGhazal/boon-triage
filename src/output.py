"""Turn decisions into the product: a per-facilitator action queue that faces
the KPI — % of Quiz-1 failers reached before Quiz 2 — not queue mechanics.

Two tiers per facilitator (the fix that makes 80% reachable at all):
  DO FIRST   calls / 1-on-1s, capped at `capacity` (facilitator time is the
             scarce resource; facilitator8 has 16 failers — a flat top-8 queue
             would cap their coverage at 50% forever)
  SEND TODAY ready WhatsApp drafts, UNCAPPED — every surfaced student leaves
             with a message (LLM draft if there are notes, template otherwise);
             heavy actions beyond capacity get their message today and wait for
             a call slot
plus a human-review lane the system never auto-acts on.

Emitted as committed CSV + JSON and a self-contained HTML page (no server — a
file:// view over the same data) with local mark-as-contacted logging and a
one-click export, so acting on the queue *generates* the outcome data the
measurement layer needs. Visual language mirrors Noon's: flat navy header,
white cards, mint accent, no gradients.
"""
from __future__ import annotations

import csv
import datetime as _dt
import html
import json
import os
import re

from . import config as C
from .decide import ActionRow, decide

PRIORITY_RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
CONCERN_RANK = {"urgent": 0, "worried": 1, "neutral": 2, "low": 3}
HEAVY = {"call_parent", "one_on_one"}   # actions that consume facilitator time


def _sort_key(row: ActionRow):
    # un-contacted failers outrank contacted ones at equal priority: the KPI is
    # coverage before Day 20, so neglect is itself a ranking signal
    return (PRIORITY_RANK[row.priority], -row.risk_score,
            row.contacted_since_quiz, CONCERN_RANK.get(row.concern, 2), row.student_id)


def build_queue(records, risks, states, capacity: int, as_of_date: str, invocation: str = None):
    rows = [decide(records[sid], risks[sid], states[sid]) for sid in records]
    surfaced = [r for r in rows if r.lane != "leave_alone"]

    by_fac: dict[str, dict] = {}
    for r in sorted(surfaced, key=_sort_key):
        fac = by_fac.setdefault(r.facilitator_email, {"priority": [], "messages": [], "review": []})
        if r.lane == "human_review":
            fac["review"].append(r)
        elif r.action_type in HEAVY and len(fac["priority"]) < capacity:
            fac["priority"].append(r)
        else:
            if r.action_type in HEAVY:
                r.call_waitlisted = True  # message goes out today; call when a slot frees
            fac["messages"].append(r)

    failers = {sid for sid, rec in records.items() if rec.quiz_failed}
    surfaced_ids = {r.student_id for r in surfaced}
    contacted = {sid for sid in failers if records[sid].contacted_since_quiz}
    days_left = (_dt.date.fromisoformat(C.NEXT_QUIZ_DATE) - _dt.date.fromisoformat(as_of_date)).days

    per_fac = {}
    for fac, g in by_fac.items():
        fac_students = [sid for sid, rec in records.items() if rec.facilitator_email == fac]
        fac_failers = [sid for sid in fac_students if sid in failers]
        per_fac[fac] = {
            "students": len(fac_students),
            "failers": len(fac_failers),
            "failers_reached_since_quiz": sum(1 for sid in fac_failers if sid in contacted),
            "priority": len(g["priority"]),
            "messages": len(g["messages"]),
            "review": len(g["review"]),
        }

    summary = {
        "as_of_date": as_of_date,
        "invocation": invocation or "(library call)",
        "capacity_per_facilitator": capacity,
        "students_total": len(records),
        "students_surfaced": len(surfaced),
        "students_left_alone": len(rows) - len(surfaced),
        "priority_actions": sum(len(f["priority"]) for f in by_fac.values()),
        "messages_today": sum(len(f["messages"]) for f in by_fac.values()),
        "human_review": sum(len(f["review"]) for f in by_fac.values()),
        "call_waitlist": sum(1 for r in surfaced if r.call_waitlisted),
        "by_priority": _count(surfaced, "priority"),
        # --- the KPI the whole system exists to move ---
        "failers_total": len(failers),
        "failers_with_action_today": len(failers & surfaced_ids),
        "failers_contacted_since_quiz": len(contacted),
        "contact_rate_pct": round(100 * len(contacted) / len(failers)) if failers else None,
        "days_to_next_quiz": days_left,
        "per_facilitator": per_fac,
    }
    return {"by_facilitator": by_fac, "surfaced": surfaced, "summary": summary}


def _count(rows, attr):
    out: dict[str, int] = {}
    for r in rows:
        out[getattr(r, attr)] = out.get(getattr(r, attr), 0) + 1
    return out


# --------------------------------------------------------------------------- #
def write_outputs(result, out_dir: str = None):
    out_dir = out_dir or C.OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    rows = sorted(result["surfaced"], key=_sort_key)

    with open(os.path.join(out_dir, "queue.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["priority", "lane", "tier", "student_id", "facilitator", "campus", "track",
                    "risk_score", "quiz_failed", "contacted_since_quiz", "note_state", "blocker",
                    "confidence", "action", "story", "phone", "phone_flag", "draft_message"])
        for r in rows:
            tier = "review" if r.lane == "human_review" else ("waitlist" if r.call_waitlisted else
                    ("priority" if r.action_type in HEAVY else "messages"))
            w.writerow([r.priority, r.lane, tier, r.student_id, r.facilitator_email, r.campus_id,
                        r.learning_track, r.risk_score, r.is_failer, r.contacted_since_quiz,
                        r.note_state, r.blocker, r.confidence, r.action_type, r.story,
                        r.phone_masked, r.phone_flag, r.draft_message])

    js = {"summary": result["summary"], "facilitators": {}}
    for fac, groups in result["by_facilitator"].items():
        js["facilitators"][fac] = {k: [_row_json(r) for r in v] for k, v in groups.items()}
    json.dump(js, open(os.path.join(out_dir, "queue.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump(result["summary"], open(os.path.join(out_dir, "run_log.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    open(os.path.join(out_dir, "action_queue.html"), "w", encoding="utf-8").write(_html(result))


def _row_json(r: ActionRow):
    return {
        "priority": r.priority, "base_tier_numbers_only": r.base_tier, "risk_score": r.risk_score,
        "student_id": r.student_id, "campus": r.campus_id, "track": r.learning_track,
        "lane": r.lane, "action": r.action_type, "call_waitlisted": r.call_waitlisted,
        "quiz_failed": r.is_failer, "contacted_since_quiz": r.contacted_since_quiz,
        "last_note_day": r.last_note_day, "note_state": r.note_state, "blocker": r.blocker,
        "confidence": r.confidence, "note_changed_priority": r.note_changed_priority,
        "story": r.story, "why": r.reasons, "evidence_ar": r.evidence,
        "draft_message_ar": r.draft_message, "parent_phone": r.phone_masked, "phone_flag": r.phone_flag,
    }


# --------------------------------------------------------------------------- #
# Presentation — Noon's flat navy + white, mint accent, no gradients.
# --------------------------------------------------------------------------- #
_STRIP = {"Critical": "#ff5d52", "High": "#fe814f", "Medium": "#f0b541", "Low": "#17e4a1"}
_TXT = {"Critical": "#e23b30", "High": "#cf5e1f", "Medium": "#a37d12", "Low": "#0e9b6b"}

_ACTION = {"call_parent": "Call parent", "one_on_one": "1-on-1 session",
           "message": "Message", "review": "Needs human review"}
_BLOCKER = {"academic": "academic", "motivation": "motivation", "family": "family",
            "health": "health", "logistics": "logistics"}
_SVG = ('<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px">{}</svg>')
_ICONS = {
    "call_parent": _SVG.format('<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6'
                               'A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1'
                               'L8.1 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z"/>'),
    "one_on_one": _SVG.format('<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>'),
    "message": _SVG.format('<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>'),
    "review": _SVG.format('<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>'),
}

_CSS = """
:root{--navy:#172740;--ink:#1b2a44;--mut:#697a92;--faint:#9aa7ba;--bg:#f7f8fa;--card:#fff;
--line:#e7eaf0;--mint:#17e4a1;--mintd:#0e9b6b;--mintbg:#eafaf3;--warn:#e23b30;--warnbg:#fdecea}
*{box-sizing:border-box} html{scroll-behavior:smooth}
body{margin:0;font-family:"IBM Plex Sans Arabic",-apple-system,Segoe UI,Roboto,sans-serif;
background:var(--bg);color:var(--ink);font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}
.hero{background:var(--navy);color:#fff;padding:34px 0 30px}
.wrap{max-width:940px;margin:0 auto;padding:0 28px}
.brand{font-size:21px;font-weight:700;letter-spacing:-.4px}
.brand i{color:var(--mint);font-style:normal} .brand b{font-weight:500;color:rgba(255,255,255,.6)}
.hero h1{margin:16px 0 4px;font-size:30px;font-weight:700;letter-spacing:-.6px}
.hero .sub{margin:0;color:rgba(255,255,255,.62);font-size:14px}
.stats{display:flex;flex-wrap:wrap;gap:38px;margin-top:24px}
.stats .n{font-size:30px;font-weight:700;line-height:1}
.stats .l{font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:rgba(255,255,255,.5);margin-top:4px}
.stats .kpi .n{color:var(--mint)}
.substats{display:flex;flex-wrap:wrap;gap:26px;margin-top:18px;font-size:12.5px;color:rgba(255,255,255,.55)}
.substats b{color:rgba(255,255,255,.85);font-weight:600}
.exp{margin-top:20px;display:inline-flex;align-items:center;gap:8px;font-size:12.5px;font-weight:600;
color:#06382a;background:var(--mint);border:0;border-radius:8px;padding:8px 14px;cursor:pointer}
main{padding:14px 0 64px}
.sec{margin-top:38px}
.sechead{display:flex;align-items:baseline;gap:12px;margin-bottom:2px;flex-wrap:wrap}
.sechead h2{font-size:13px;letter-spacing:.07em;text-transform:uppercase;color:var(--navy);margin:0;font-weight:700}
.sechead .m{font-size:12.5px;color:var(--faint)}
.sechead .cov{margin-inline-start:auto;font-size:12.5px;color:var(--mintd);font-weight:600}
.lanelbl{font-size:11px;letter-spacing:.06em;text-transform:uppercase;font-weight:700;margin:20px 0 0;color:#31537d}
.lanelbl.msg{color:var(--mintd)} .lanelbl.rev{color:#7c5ce1}
.card{background:var(--card);border:1px solid var(--line);border-top:3px solid #ccc;border-radius:14px;
padding:18px 20px;margin-top:14px;box-shadow:0 1px 2px rgba(20,40,80,.04);transition:opacity .2s}
.card.done{opacity:.45}
.r1{display:flex;align-items:center;gap:11px;flex-wrap:wrap}
.sid{font-weight:700;font-size:18px;color:var(--navy);letter-spacing:-.3px}
.pri{font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase}
.tag{font-size:12px;color:var(--mintd);border:1px solid #bdeede;border-radius:100px;padding:2px 11px;background:var(--mintbg)}
.tag.warn{color:var(--warn);border-color:#f5c6c0;background:var(--warnbg)}
.tag.mut{color:var(--mut);border-color:var(--line);background:#f2f4f7}
.cta{margin-inline-start:auto;display:inline-flex;align-items:center;gap:7px;font-size:13px;font-weight:600;
color:#06382a;background:var(--mint);border-radius:8px;padding:8px 15px;white-space:nowrap}
.review .cta{background:#efeaff;color:#4b32a8}
.story{margin:13px 0 0;font-size:15px;color:#33415c}
ul.why{list-style:none;padding:0;margin:10px 0 0}
ul.why li{position:relative;padding-inline-start:16px;font-size:13px;color:var(--mut);margin-top:4px}
ul.why li::before{content:"";position:absolute;inset-inline-start:2px;top:8px;width:5px;height:5px;border-radius:50%;background:#c3ccda}
.note{background:var(--mintbg);border:1px solid #d6f2e6;border-radius:11px;padding:11px 14px;margin-top:13px}
.dlbl{font-size:9.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--mintd);font-weight:600;margin-bottom:4px}
.dlbl.s{margin-top:11px}
.ev{direction:rtl;text-align:right;color:#0c6e4d;font-size:14px}
.draft{direction:rtl;text-align:right;font-size:15px;color:#26354f;line-height:1.75}
.meta{display:flex;align-items:center;gap:14px;flex-wrap:wrap;font-size:11.5px;color:var(--faint);
margin-top:13px;border-top:1px solid var(--line);padding-top:10px}
.meta b{color:var(--mut);font-weight:600}
.done-toggle{margin-inline-start:auto;display:inline-flex;align-items:center;gap:6px;font-size:12px;
font-weight:600;color:var(--mintd);cursor:pointer;user-select:none}
.done-toggle input{accent-color:var(--mintd);width:15px;height:15px;cursor:pointer}
.lift{font-size:10px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--mintd);background:var(--mintbg);border-radius:100px;padding:2px 9px}
.review .card{border-top-color:#7c5ce1}
footer{margin-top:46px;border-top:1px solid var(--line);padding-top:16px;font-size:12px;color:var(--faint)}
@media(max-width:600px){.hero h1{font-size:24px}.stats{gap:22px}.cta{margin-inline-start:0}}
"""

_JS = """
(function(){
  var KEY = "boon.contacted.__ASOF__";
  var store = {};
  try { store = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch(e) {}
  function save(){ try { localStorage.setItem(KEY, JSON.stringify(store)); } catch(e) {} }
  function refresh(){
    var n = Object.keys(store).length;
    var el = document.getElementById("logged-n");
    if (el) el.textContent = n;
  }
  document.querySelectorAll(".done-toggle input").forEach(function(cb){
    var sid = cb.getAttribute("data-sid");
    if (store[sid]) { cb.checked = true; cb.closest(".card").classList.add("done"); }
    cb.addEventListener("change", function(){
      if (cb.checked) store[sid] = {at: new Date().toISOString(), action: cb.getAttribute("data-action"), fac: cb.getAttribute("data-fac")};
      else delete store[sid];
      cb.closest(".card").classList.toggle("done", cb.checked);
      save(); refresh();
    });
  });
  var exp = document.getElementById("export-log");
  if (exp) exp.addEventListener("click", function(){
    var lines = ["student_id,facilitator,action,marked_contacted_at"];
    Object.keys(store).sort().forEach(function(sid){
      var v = store[sid];
      lines.push([sid, v.fac, v.action, v.at].join(","));
    });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([lines.join("\\n")], {type: "text/csv"}));
    a.download = "contact_log___ASOF__.csv";
    a.click();
  });
  refresh();
})();
"""


def _fac_name(email):
    m = re.match(r"([a-zA-Z]+?)\s*0*(\d+)", email.split("@")[0])
    return f"{m.group(1).capitalize()} {m.group(2)}" if m else email.split("@")[0].capitalize()


def _esc(x):
    return html.escape(str(x))


def _html(result) -> str:
    s = result["summary"]
    contact_pct = s["contact_rate_pct"] if s["contact_rate_pct"] is not None else "—"
    head = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Boon Academy — Intervention Queue</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{_CSS}</style></head><body>
<header class="hero"><div class="wrap">
<div class="brand">bo<i>o</i>n <b>academy</b></div>
<h1>Who to help first — and why</h1>
<p class="sub">As of {s['as_of_date']} · Quiz 2 in <b>{s['days_to_next_quiz']} days</b> · calls capped at {s['capacity_per_facilitator']} per facilitator · messages never capped</p>
<div class="stats">
<div class="kpi"><div class="n">{s['failers_with_action_today']}/{s['failers_total']}</div><div class="l">Quiz-1 failers · action ready today</div></div>
<div><div class="n" style="color:#ffb1aa">{s['failers_contacted_since_quiz']}<span style="font-size:16px;color:rgba(255,255,255,.45)"> ({contact_pct}%)</span></div><div class="l">Failers contacted since Quiz 1</div></div>
<div><div class="n" style="color:#ff6a60">{s['by_priority'].get('Critical', 0)}</div><div class="l">Critical</div></div>
<div><div class="n" style="color:rgba(255,255,255,.85)"><span id="logged-n">0</span></div><div class="l">Marked contacted (this device)</div></div>
</div>
<div class="substats">
<span><b>{s['priority_actions']}</b> calls / 1-on-1s</span>
<span><b>{s['messages_today']}</b> ready messages</span>
<span><b>{s['human_review']}</b> human review</span>
<span><b>{s['call_waitlist']}</b> on the call waitlist</span>
<span><b>{s['students_left_alone']}</b> left alone</span>
</div>
<button class="exp" id="export-log">⬇ Export contact log (CSV)</button>
</div></header>
<main><div class="wrap">"""

    parts = [head]
    for fac, g in result["by_facilitator"].items():
        k = s["per_facilitator"].get(fac, {})
        parts.append(
            f'<section class="sec"><div class="sechead"><h2>{_esc(_fac_name(fac))}</h2>'
            f'<span class="m">{k.get("students", "?")} students · {k.get("failers", "?")} failed Quiz 1</span>'
            f'<span class="cov">reached {k.get("failers_reached_since_quiz", 0)}/{k.get("failers", 0)} failers since Quiz 1</span></div>')
        if g["priority"]:
            parts.append(f'<div class="lanelbl">Do first — calls &amp; 1-on-1s (top {s["capacity_per_facilitator"]})</div>')
            for r in g["priority"]:
                parts.append(_card(r))
        if g["messages"]:
            parts.append('<div class="lanelbl msg">Send today — ready messages (uncapped)</div>')
            for r in g["messages"]:
                parts.append(_card(r))
        if g["review"]:
            parts.append('<div class="lanelbl rev">Needs human review</div><div class="review">')
            for r in g["review"]:
                parts.append(_card(r))
            parts.append("</div>")
        parts.append("</section>")
    parts.append('<footer>Boon Academy · the LLM reads the Arabic notes, deterministic rules decide, '
                 'the facilitator sends · mark-as-contacted stays on this device; export it to close the loop.</footer>')
    parts.append(f"</div></main><script>{_JS.replace('__ASOF__', s['as_of_date'])}</script></body></html>")
    return "".join(parts)


def _card(r: ActionRow) -> str:
    strip, txt = _STRIP[r.priority], _TXT[r.priority]
    chips = [f'<span class="tag">{_esc(r.learning_track)}</span>', f'<span class="tag">{_esc(r.campus_id)}</span>']
    if r.blocker in _BLOCKER:
        chips.append(f'<span class="tag mut">blocker: {_BLOCKER[r.blocker]}</span>')
    if r.is_failer and not r.contacted_since_quiz:
        chips.append('<span class="tag warn">no contact since Quiz 1</span>')
    elif r.contacted_since_quiz and r.last_note_day:
        chips.append(f'<span class="tag mut">contacted Day {r.last_note_day}</span>')
    if r.last_note_day is None:
        chips.append('<span class="tag mut">no notes yet — log one line after contact</span>')
    if r.call_waitlisted:
        chips.append('<span class="tag warn">call when a slot frees — message today</span>')
    if r.note_changed_priority:
        chips.append('<span class="lift">notes moved this</span>')
    cta = f'<span class="cta">{_ICONS.get(r.action_type, _ICONS["message"])}{_ACTION.get(r.action_type, r.action_type)}</span>'
    why = "".join(f"<li>{_esc(x)}</li>" for x in r.reasons[:3])
    note = ""
    if r.evidence or r.draft_message:
        ev = f'<div class="dlbl">From the note</div><div class="ev">“{_esc(r.evidence)}”</div>' if r.evidence else ""
        sc = " s" if r.evidence else ""
        dr = (f'<div class="dlbl{sc}">WhatsApp draft — sent by the facilitator</div>'
              f'<div class="draft">{_esc(r.draft_message)}</div>') if r.draft_message else ""
        note = f'<div class="note">{ev}{dr}</div>'
    toggle = (f'<label class="done-toggle"><input type="checkbox" data-sid="{_esc(r.student_id)}" '
              f'data-action="{_esc(r.action_type)}" data-fac="{_esc(r.facilitator_email)}"> mark contacted</label>')
    return f"""<article class="card" style="border-top-color:{strip}">
<div class="r1"><span class="pri" style="color:{txt}">{_esc(r.priority)}</span>
<span class="sid">{_esc(r.student_id)}</span>
{''.join(chips)}{cta}</div>
<p class="story">{_esc(r.story)}</p>
<ul class="why">{why}</ul>{note}
<div class="meta">parent <b>{_esc(r.phone_masked)}</b> ({_esc(r.phone_flag)}) · note-state <b>{_esc(r.note_state)}</b> · confidence <b>{_esc(r.confidence)}</b>{toggle}</div></article>"""
