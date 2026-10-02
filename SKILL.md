---
name: jev-questions
description: Designing typed questions for Jev / TypeSafe System One — Noul, Choice and Score — and debugging ones that do not work. Use when building a judge, gate, filter, classifier or extractor on System One; when writing or revising `instructions` and `criteria`; when a question fires on everything or on nothing; when deciding whether a job belongs to the model or to code; or when choosing thresholds. Covers what makes criteria answerable, how to tell a working question from a constant one, and the failure patterns that look like model errors but are not.
---

# Designing questions for System One

System One returns typed judgments, not text. You supply **state** (the data) and
**questions**; you get a probability per Noul, a distribution per Choice, a level per
Score. Everything below is about making those judgments mean something.

These are lessons from building and measuring a real system, including several learned
by getting them wrong first. Where a number appears, it was measured.

## 1. Criteria describe situations, never words

**This is the rule that matters most, and it is the easiest to break twice.**

A question that enumerates surface forms is handing a lexical rule to a model that reads
meaning. It will do what you asked and be wrong.

```python
# WRONG - a word list
criteria=NoulCriteria(
    true="Opens on 'and so', 'but then', 'yeah exactly'",
    false="Opens on a complete thought",
)
```

Against real speech this fired on nearly every excerpt, because people talk in
connectives. The obvious "fix" is the same mistake inverted:

```python
# STILL WRONG - the same list, pointing the other way
false="Beginning with 'and', 'but' or 'so' is normal speech and is fine",
```

Describe what is true of the *content*:

```python
# RIGHT
criteria=NoulCriteria(
    true="The opening depends on something the viewer was not given: it finishes a "
         "thought that began earlier, or replies to something said before the clip",
    false="The opening carries enough on its own for the viewer to follow it from "
          "the first line",
)
```

**When a question fires on a neighbouring situation, name the distinction in the question.**
A question meant to catch clips that depend on a live audience listed "an answer called
back, a reaction the speaker replies to" — and flagged ordinary panel cross-talk, because
every panel reply is one. Dropping the examples fixed the false flags but also stopped it
catching real audience votes. What worked was asking outright: *several speakers talking
with each other, or an audience listening who are not speakers — which does the point
depend on?* False flags fell from 23 of 92 to 1. The model could always make the
distinction; it had not been asked to.

Same for Score levels. "Levels must describe situations" is in the official Score
guidance; numbers-only levels collapse to confidence ~0.5.

## 2. Check that your question can discriminate

A question whose honest answer is *"kind of"* for every case cannot gate anything. The
model is not failing — you asked something that is mildly true of everything.

**Diagnostic: run it over a sample and look at the spread.**

```
                     median   range        spread
ends_mid_thought       0.39   0.15-0.88      0.25   <- works
starts_mid_thought     0.66   0.41-0.82      0.13   <- nearly constant
dangling_reference     0.68   0.39-0.80      0.12   <- nearly constant
```

The first separates cases confidently. The others sit in a narrow band and carry almost
no information — and a 0.5 threshold on a distribution centred at 0.66 then rejects
nearly everything, which looks like a strict model and is actually a bad question.

If the spread is small, do not move the threshold. Fix the question or drop it.

**The test rejects; it does not select.** On a few dozen items it will tell you a
question is a constant. It will not tell you which of two working questions is better —
a 0.18 against a 0.16 is noise at that size. Use it as a filter before wiring a question
in, never as an optimiser to pick between wordings, or you are fitting to your sample.

**Measure on the unfiltered population.** A question that gates hard has its high scorers
removed from whatever you measure next, so it reads flatter than it is. One question in a
real gate measured 0.13 on the survivors of ten items and 0.17 across thirty-eight — it
was fine, and the first number was its own rejections biting. The spread you can trust
without correction is a question that has *never* fired: nothing has been truncated.

**A question that never fires is either a safety net or dead weight, and the difference
is whether it would catch anything.** Check it against the cases you know are bad. If it
scores them the same as the good ones, it is not a net.

**Corollary:** never report a hit rate without the rate chance would give at the same
density. A method that fires often hits often by luck.

## 3. Pick the primitive for the shape of the judgment

| | use when | watch for |
| --- | --- | --- |
| **Noul** | an absolute yes/no about the state | each is independent; all of them can be low at once |
| **Choice** | pick one of N things code enumerated | probability is always distributed, so a high score means "best of these", not "this is real" |
| **Score** | graded quality on levels you define | never interpolate a magnitude between levels; use the expectation for threshold checks only |

**A Choice needs an escape option** (`none_of_these`) or it will confidently pick the
least-bad option from a list where nothing applies.

**Noul and Choice numbers are not comparable.** One is absolute, one is relative. A
threshold tuned on one is meaningless on the other.

**The escape option's probability is a second detector.** `max(p_noul, 1 - p_none)`
gives you two independent views of one state for no extra cost: a case with unusual
wording can score low on the Noul and still put little weight on "none".

**When a Choice's top pick fails a downstream check, retry its own order — don't
re-rank the survivors yourself.** A Choice over candidate openings, each then verified
against the finished clip, does better trying the Choice's 2nd and 3rd picks in the
Choice's own order than re-sorting the candidates that passed by a separate raw
criterion score (fully-right clips 35→38 with the Choice's order, 35→33 re-ranked by
`hook` alone). The Choice already weighed everything you'd re-rank on and more; a single
criterion score you compute afterward is a strictly narrower view of the same case.

**Keep the distribution, not just the answer.** A Score of 1.0 can mean all weight on
level 1, or a split between 0 and 2. Only the spread tells them apart. Confidence is
distribution concentration, not permission to act — measured on one task, accuracy was
*flat* across every confidence band, so no threshold isolated the good answers.

## 4. State: put the model exactly where the judge sits

If you are asking "would a reader understand this on its own", show it **only what the
reader gets**. Add the surrounding context to be helpful and the model resolves what the
reader cannot, and tells you everything is fine.

This is the one thing not to "improve".

Other state rules:

- **Address things by ID.** Render rows as `L042| text…`, let the model return `L042`,
  and map it back in code. The model never emits a number it would have to compute.
- IDs may contain digits. The constraint is arithmetic and ordering, not the presence of
  a numeral — and in a Choice the model never writes the ID at all, it puts weight on an
  option you enumerated. The real risk is **confusability** between adjacent IDs, which
  you measure (how often are the top two options neighbours with a close margin), not
  argue about.
- **Do not duplicate content into option descriptions** when the state already carries
  the text. Bare IDs with `None` descriptions is the intended pattern.
- **An instruction that names one piece of state as the anchor gets followed past the
  point where that item stops being right.** "Cut around the line `region.moment`" meant
  *roughly here* — but when the marked line was actually the close of the thought before
  the real moment, the model kept it as the opening anyway, because it had been told that
  line was where to cut. It was not confused; it did what the instruction said. Naming
  state in an instruction makes it authoritative, not just a hint — if the caller can't
  guarantee the pointer is always right, say so, or offer a range instead of a point.
- Never ask the model to compare, count or order IDs. That is arithmetic and it will
  fail. Order comes from code, and from the state already being in order.

## 5. Many questions, one state, one request

Question definitions are tiny next to the state. Asking seven questions about one
document in one request costs barely more than asking one, and the answers are
consistent with each other. Splitting into "ask the cheap one first, then the rest" is
usually a false economy — decide the *order of the policy*, not the order of requests.

## 6. Do not ask for a number you are about to compute

If you score dimensions separately and then combine them in code — the composite-scoring
pattern — do not also ask the model for the combination. "Is this any good?" alongside
"how strong is the opening" and "does it deliver" is the same judgment twice, once in the
model and once in your weights.

It also cannot discriminate, for a reason worth internalising: **a general evaluative
question put to an already-filtered population is asking whether your filter worked.** If
an earlier stage selected for "worth attention", then "is this worth having?" is answered
yes, uniformly, by construction.

The questions that survive contact with real data ask about something **specific and
locatable** — does it stop before the point arrives, does the payoff happen somewhere the
viewer cannot see. You can point at the text and check. The ones that go flat ask for a
verdict: is this good, is this worth it, does this stand alone.

Prefer the narrow, checkable question. If you cannot name what in the text would make it
true, the model cannot either.

## 7. Separate judgment from policy

Return what the model said. Apply thresholds somewhere else.

```python
verify(...) -> Judgment   # nouls, scores, confidence, distributions. No decisions.
verdict(j)  -> Verdict    # thresholds live here, and they are all placeholders
```

Thresholds are guesses until calibrated on labelled data. Keeping them out of the
judgment means recalibrating does not invalidate stored results.

**Calibrate a threshold against the hardest real instance of what you're catching, not
the clean whole one.** A check for sponsor reads caught 94% of whole reads at 0.5 — and
50% of the same reads' *middle 30 seconds*, cut the way real edits actually trim them.
Whole examples are the easy case; the population you'll actually see is partial. Moving
the bar to 0.35 — set from where real content peaks (0.41) and where the hardest
violations sit (0.40-0.47), not a round-number guess — caught 82% of the middles for one
borderline real clip lost. Construct the harder sub-population deliberately and measure
on it; the easy case will pass at almost any threshold and tells you nothing.

**Order the policy by repairability.** Check the irreparable things first — if the answer
means "this can never be good", stop. Only then check the things a caller can fix, and
return *what to do* rather than just a pass/fail. Conflating "bad thing" with "badly
presented thing" throws away good material: in one system, quality was measured and then
ignored by the verdict, so bland items with tidy edges shipped while strong ones with a
ragged edge were dropped.

## 8. Know where the model actually beats code

Measured, on the same data:

- A Choice over enumerated boundary candidates **lost** to a tuned constant offset
  (8.7s vs 5.5s median error). Where the target sits at a near-fixed distance from a
  known anchor, arithmetic is near-optimal and a model adds nothing.
- The same model caught that a clip opening `"Pure luck."` was answering a question the
  clip did not contain. No offset, snap or rule can do that — there is nothing to
  compute.

**Spend the model where there is no computable proxy.** If a constant, a regex or a
sort can approximate the answer, measure them first — they are free, and they are the
baseline you have to beat before the request is worth making.

## 9. Failure patterns that look like model errors

| symptom | usual cause |
| --- | --- |
| fires on everything | question is mildly true of everything (check the spread) |
| fires on nothing | threshold set for a distribution the question does not have |
| confident and wrong | criteria describe surface forms, not situations |
| Choice picks something implausible | no escape option, so it returned the best of a bad list |
| right answer never chosen | **it was never in the option list** — check candidate coverage before blaming the model |
| a degraded result looks healthy | partial input was not marked as partial; carry coverage with the result |
| a judgment is right but lands at the wrong time | it depends on text a later stage still changes. Judge on what actually ships, not on an intermediate draft |

The second-to-last is the one that masquerades as every other. A model cannot choose an
option you did not offer, and in the logs that is indistinguishable from a bad judgment.
Check coverage first, always.
