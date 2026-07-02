# Gold-label codebook — facilitator-note state extraction

**What this is.** Human adjudicated labels for all 75 note threads (180 notes,
clamped to Day 14), used to measure the LLM extractor in `src/eval_extractor.py`.
Labels were drafted from the **notes only** — the same input the extractor sees:
no attendance, practice, or quiz numbers — and **before** the v3 extractor ran,
so nothing here is fitted to model output.

**Unit.** One label per student thread, describing the state **as of the latest
notes** (the thread is dated; the newest decisive information wins).

## States (mutually exclusive; apply the first rule that matches)

1. **refused** — the parent or student **explicitly declined or pushed back on
   offered help**: a defensive parent rejecting the concern, a rejected offer of
   extra help, quitting the program. A student merely not doing exercises is
   NOT refused (that's the problem, not a refusal of help).
2. **failing** — help **was attempted** (calls, talks, messages) and the
   situation is **not improving**: unreachable parents, no change despite given
   guidance ("لسا على نفس الوضع"), worsening. Includes undeliverable contact.
3. **explained** — the problem (usually an absence) has a **known, managed,
   likely temporary cause** — illness, a family event — **and the parent is
   aware or was contacted**. Monitoring is enough for now.
4. **improving** — was struggling, now **clearly better**, or an intervention is
   visibly working ("تحول كبير", rising practice, a thank-you call). Slow-but-
   real progress counts ("التقدم بطيء بس موجود").
5. **needs_help** — a real problem (academic, motivational, family, emotional)
   with **no working intervention yet** — including notes that only state intent
   ("لازم نتدخل") and unexplained worry. This is the default for real problems
   that fit nothing above.
6. **none** — purely administrative or positive-only notes ("طالبة ممتازة");
   nothing to act on.

## Blocker (secondary label — what stands in the way)

`academic` (weak concepts, easy-only practice, cramming, behind after absence) ·
`motivation` (sees no value, refuses to practice, fear of hard questions / low
confidence) · `family` (parent unaware of program, family crisis, parental
anxiety) · `health` (illness, fatigue) · `logistics` (schedule/transport,
night-shift parent, unreachable phone as a *technical* matter) · `unknown`
(the notes never say — generic "متعثر، يحتاج تدخل" threads).

## Ambiguity policy

Threads that genuinely support two readings carry `ambiguous=yes` plus an
`alt_state`. The eval reports **strict** agreement (gold only) and **lenient**
agreement (gold or alt). Disagreements on ambiguous rows are noted, not treated
as extractor errors, in the qualitative review.

## Provenance

Drafted by the author from `data/facilitator_notes.csv` on the case clock's
Day 14; adjudicated once against the codebook above. Single-rater labels — a
second Arabic-speaking rater (planned) turns the reported agreement into a real
inter-rater κ. Treat per-state numbers as directional at n=75.
